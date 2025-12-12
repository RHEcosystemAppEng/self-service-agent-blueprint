#!/bin/bash

set -e

# Configuration
REPO="RHEcosystemAppEng/self-service-agent-blueprint"
DOWNLOAD_DIR="./nightly_test_results"

# Check if GITHUB_TOKEN is set
if [ -z "$GITHUB_TOKEN" ]; then
    echo "Error: GITHUB_TOKEN environment variable is not set"
    exit 1
fi

# Function to parse log file and extract failed conversations
parse_failed_conversations() {
    local log_file="$1"
    local results_dir="$2"

    if [ ! -f "$log_file" ]; then
        echo "    ⚠️  Log file not found: $log_file"
        return 1
    fi

    echo ""
    echo "    📋 Analyzing failures from log..."

    # Extract overall failure count
    local overall_result=$(grep "⚠️  OVERALL RESULT:" "$log_file" 2>/dev/null || echo "")
    if [ -n "$overall_result" ]; then
        echo "    $overall_result"
    fi

    # Find all failed conversations
    local failed_convos=$(grep -E "❌.*generated_flow_worker.*\.json:.*metrics passed" "$log_file" 2>/dev/null || true)

    if [ -z "$failed_convos" ]; then
        echo "    ℹ️  No specific conversation failures found in log"
        return 0
    fi

    echo ""
    echo "    Failed Conversations:"
    echo "    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Parse each failed conversation
    local count=0
    while IFS= read -r line; do
        count=$((count + 1))

        # Extract conversation file name and metrics
        local conv_file=$(echo "$line" | grep -o 'generated_flow_worker[0-9_]*\.json' || echo "Unknown")
        local metrics=$(echo "$line" | grep -o '[0-9]*/[0-9]* metrics passed' || echo "Unknown")

        echo "    $count. $conv_file ($metrics)"

        # Find the failed metrics for this conversation by looking ahead in the log
        # We'll use awk to find the section in the CONVERSATION SUMMARY
        local failed_metrics=$(awk -v conv="$conv_file" '
            /CONVERSATION SUMMARY:/ { in_summary=1 }
            in_summary && $0 ~ conv && /❌/ { found=1; next }
            found && /Failed metrics:/ { in_metrics=1; next }
            found && in_metrics && /•/ {
                # Extract just the metric description after the bullet
                match($0, /•(.*)/, arr)
                if (arr[1] != "") {
                    gsub(/^[[:space:]]+/, "", arr[1])
                    print "       • " arr[1]
                }
            }
            found && in_metrics && (/✅|^[0-9]{4}-.*❌/) { found=0; in_metrics=0 }
        ' "$log_file")

        if [ -n "$failed_metrics" ]; then
            echo "$failed_metrics" | head -5  # Limit to first 5 lines to keep output manageable
        fi

        # Display the full conversation if results directory is provided
        if [ -n "$results_dir" ] && [ -d "$results_dir" ]; then
            local conv_path="$results_dir/results/conversation_results/$conv_file"
            if [ -f "$conv_path" ]; then
                echo ""
                echo "       📁 Full path: $(realpath "$conv_path")"
                echo ""
                echo "       📝 Full Conversation (JSON):"
                echo "       ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"
                # Display the raw JSON with proper indentation
                jq '.' "$conv_path" 2>/dev/null | sed 's/^/       /' || cat "$conv_path" | sed 's/^/       /'
                echo "       ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"
            else
                echo ""
                echo "       ⚠️  Conversation file not found: $conv_path"
            fi
        fi

        echo ""
    done <<< "$failed_convos"

    echo "    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "    Total failed conversations: $count"
}

# Clean up and create download directory
rm -rf "$DOWNLOAD_DIR"
mkdir -p "$DOWNLOAD_DIR"

echo "Fetching nightly workflows..."
echo "================================================"

# Get all workflows and filter for ones with "Nightly" in the name
workflows=$(curl -s -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github.v3+json" \
    "https://api.github.com/repos/${REPO}/actions/workflows")

nightly_workflows=$(echo "$workflows" | jq -r '.workflows[] | select(.name | contains("Nightly") or contains("nightly")) | "\(.id)|\(.name)"')

if [ -z "$nightly_workflows" ]; then
    echo "No nightly workflows found"
    exit 0
fi

echo "Found $(echo "$nightly_workflows" | wc -l) nightly workflow(s)"
echo ""

FAILURES_FOUND=0
DOWNLOADED_RESULTS=()

while IFS='|' read -r workflow_id workflow_name; do
    echo "Checking: $workflow_name (ID: $workflow_id)"

    # Get the most recent run for this workflow
    latest_run=$(curl -s -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/vnd.github.v3+json" \
        "https://api.github.com/repos/${REPO}/actions/workflows/${workflow_id}/runs?per_page=1" \
        | jq -r '.workflow_runs[0] // empty')

    if [ -z "$latest_run" ]; then
        echo "  ⚠️  No runs found for this workflow"
        echo ""
        continue
    fi

    run_id=$(echo "$latest_run" | jq -r '.id')
    run_number=$(echo "$latest_run" | jq -r '.run_number')
    conclusion=$(echo "$latest_run" | jq -r '.conclusion // "in_progress"')
    created_at=$(echo "$latest_run" | jq -r '.created_at')

    echo "  Latest run: #$run_number (ID: $run_id)"
    echo "  Created: $created_at"
    echo "  Status: $conclusion"

    if [ "$conclusion" == "failure" ]; then
        echo "  ❌ FAILED - Downloading evaluation results and logs..."
        FAILURES_FOUND=$((FAILURES_FOUND + 1))

        # Create directory for this run
        run_dir="${DOWNLOAD_DIR}/run_${run_id}"
        mkdir -p "$run_dir"

        # Download action logs
        echo "    Downloading action logs..."
        logs_file="${run_dir}/action_logs.zip"
        curl -L -s -H "Authorization: Bearer ${GITHUB_TOKEN}" \
            -H "Accept: application/vnd.github.v3+json" \
            "https://api.github.com/repos/${REPO}/actions/runs/${run_id}/logs" \
            -o "$logs_file"

        if [ -f "$logs_file" ]; then
            file_size=$(ls -lh "$logs_file" | awk '{print $5}')
            echo "    ✓ Downloaded logs: $logs_file ($file_size)"

            # Extract logs
            logs_dir="${run_dir}/logs"
            mkdir -p "$logs_dir"
            unzip -q "$logs_file" -d "$logs_dir" 2>/dev/null || echo "    ⚠️  Log extraction had warnings"
            rm "$logs_file"
        else
            echo "    ⚠️  Failed to download logs"
        fi

        # Get artifacts for this run
        artifacts=$(curl -s -H "Authorization: Bearer ${GITHUB_TOKEN}" \
            -H "Accept: application/vnd.github.v3+json" \
            "https://api.github.com/repos/${REPO}/actions/runs/${run_id}/artifacts")

        artifact_count=$(echo "$artifacts" | jq -r '.total_count // 0')

        if [ "$artifact_count" -eq 0 ]; then
            echo "  ⚠️  No artifacts found for this run"
        else
            # Download each evaluations-results artifact
            while IFS='|' read -r artifact_id artifact_name download_url; do
                output_file="${run_dir}/${artifact_name}.zip"

                echo "    Downloading artifact: $artifact_name"
                curl -L -s -H "Authorization: Bearer ${GITHUB_TOKEN}" \
                    -H "Accept: application/vnd.github.v3+json" \
                    "$download_url" -o "$output_file"

                if [ -f "$output_file" ]; then
                    file_size=$(ls -lh "$output_file" | awk '{print $5}')
                    echo "    ✓ Downloaded: $output_file ($file_size)"

                    # Extract the artifact (zip containing tar.gz)
                    unzip -q "$output_file" -d "$run_dir"

                    # Check if there's a tar.gz inside and extract it
                    tar_file=$(find "$run_dir" -name "*.tar.gz" -type f | head -1)
                    if [ -n "$tar_file" ]; then
                        tar -xzf "$tar_file" -C "$run_dir"
                        rm "$tar_file"  # Clean up the tar.gz
                    fi

                    # Clean up the zip file
                    rm "$output_file"

                    # Check if extraction was successful
                    if [ -d "$run_dir/results" ]; then
                        echo "    ✓ Extracted to: $run_dir"
                        DOWNLOADED_RESULTS+=("$run_dir")
                    else
                        echo "    ⚠️  Extraction may have failed or unexpected structure"
                    fi
                else
                    echo "    ❌ Download failed"
                fi
            done < <(echo "$artifacts" | jq -r '.artifacts[] | select(.name | contains("evaluations-results")) | "\(.id)|\(.name)|\(.archive_download_url)"')
        fi

        # Now that both logs and artifacts are downloaded, parse the failures with full conversation details
        main_log=$(find "${run_dir}/logs" -name "*Run e2e tests.txt" -o -name "*Run*test*.txt" 2>/dev/null | head -1)
        if [ -n "$main_log" ]; then
            echo ""
            parse_failed_conversations "$main_log" "$run_dir"
        fi

    elif [ "$conclusion" == "success" ]; then
        echo "  ✓ Passed"
    else
        echo "  ⏳ $conclusion"
    fi

    echo ""
done <<< "$nightly_workflows"

# Count total workflows checked
TOTAL_WORKFLOWS=$(echo "$nightly_workflows" | wc -l)

echo "================================================"
echo "Summary:"
echo "  Total nightly workflows checked: $TOTAL_WORKFLOWS"
echo "  Workflows with failures: $FAILURES_FOUND"
echo ""

if [ $FAILURES_FOUND -gt 0 ]; then
    echo "Downloaded evaluation results locations:"
    for result_dir in "${DOWNLOADED_RESULTS[@]}"; do
        echo "  - $result_dir"
        if [ -f "$result_dir/results/deep_eval_results/deepeval_all_results.json" ]; then
            echo "    ├─ deepeval_all_results.json: $(realpath "$result_dir/results/deep_eval_results/deepeval_all_results.json")"
        fi
        if [ -d "$result_dir/logs" ]; then
            echo "    └─ action logs: $(realpath "$result_dir/logs")"
        fi
    done
else
    echo "✓ All nightly workflows passed (or no failures found)"
fi
