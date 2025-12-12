# Review Nightly Test Failures

Run the nightly test failure analysis and generate a comprehensive report.

## Task

use the script .claude/scripts/check_nightly_failures.sh to get the results for the last nightly runs.

The script accepts an optional date parameter in YYYY-MM-DD format. If a date is provided, the analysis will use the last nightly runs as of that date instead of the most recent runs. If the user provides a date with this command, pass it to the script as the first argument.

For any runs that failed, generate a summary that indicates for each action run:
1) was there failures or not
2) If there were failures, the specific runs that failed
3) for each specific run that failed if it was a valid failure or not based on laptop information in agent-service/config/knowledge_bases/laptop-refresh
4) as summary of the failure as reported in the log and the related part of the conversation from the conversation in the evaluation results 

You should already have info for failures in the output from check_nightly_failures.sh and should not have to look at the logs or conversation files.

When showing a file for a run like generated_flow_xxxx include the full path to the file, and validate that you got the full path correct

Do not add any additional route cause analysis

## Example Output

Here's an example of the expected report format:

```
# Nightly Test Failure Analysis Report
**Date:** 2025-12-12

## Summary

Out of 4 nightly workflow runs analyzed, **1 workflow failed** with **3 conversation failures**.

### Workflows Status:

1. ✓ **(Scout Prompt) Nightly 20 conversation test** - Run #48 (ID: 20157166126) - **PASSED**
2. ❌ **(Small Prompt) Nightly 20 conversation test** - Run #50 (ID: 20156469756) - **FAILED**
3. ✓ **Pull Request - Nightly 20 conversation test** - Run #64 (ID: 20155733765) - **PASSED**
4. ✓ **Prod deploy - Nightly 20 conversation test** - Run #40 (ID: 20158320314) - **PASSED**

---

## Detailed Failure Analysis: (Small Prompt) Nightly 20 conversation test

**Run ID:** 20156469756
**Created:** 2025-12-12T04:38:13Z
**Overall Result:** 3 conversations failed out of 20

---

### Failure 1: generated_flow_worker0_18_20251212_050546.json

**File Path:** `/home/midawson/newpull/self-service-agent-blueprint/nightly_test_results/run_20156469756/results/conversation_results/generated_flow_worker0_18_20251212_050546.json`

**User:** david.chen@company.com (APAC region)

**Metrics:** 13/15 passed

#### Failed Metrics:

1. **No errors reported by agent** (score: 0.800)
   - **Failure Summary:** The assistant apologized for having difficulty generating a response and asked the user to try again, which temporarily disrupted the conversation flow.
   - **Valid Failure:** ✓ **YES** - This is a legitimate error where the agent failed to respond properly mid-conversation.

2. **Correct laptop options for user location** (score: 0.000)
   - **Failure Summary:** The agent failed to present all available laptop models for the user's location (APAC). The agent provided information about the ZenBook Pro 15, which is **NOT** listed in the APAC laptop offerings, and did not include the required 15 specification fields for each laptop model.
   - **Valid Failure:** ✓ **YES** - The ZenBook Pro 15 is not in the APAC laptop offerings. The valid APAC options are:
     - MacBook Air M2
     - MacBook Pro 14 M3
     - ThinkPad T14 Gen 5 AMD
     - ThinkPad P1 Gen 6

#### Conversation Summary:
User requested laptop refresh → Agent confirmed eligibility → Agent had technical error ("difficulty generating a response") → Agent failed to list laptop options → User selected ZenBook Pro 15 (invalid for APAC) → Ticket created (REQ8523445)

---

### Failure 2: generated_flow_worker0_9_20251212_045649.json

**File Path:** `/home/midawson/newpull/self-service-agent-blueprint/nightly_test_results/run_20156469756/results/conversation_results/generated_flow_worker0_9_20251212_045649.json`

**User:** maria.garcia@company.com (LATAM region)

**Metrics:** 12/15 passed

#### Failed Metrics:

1. **Option Presentation** (score: 0.600)
   - **Failure Summary:** The assistant failed to present laptop options based on the user's location when engaged in the laptop refresh process. However, it did provide complete specifications for the selected laptop and guided the user through creating a ServiceNow ticket.
   - **Valid Failure:** ✓ **YES** - Agent should have presented the LATAM laptop options before asking user to select.

2. **No errors reported by agent** (score: 0.800)
   - **Failure Summary:** The assistant apologized for having difficulty generating a response and asked the user to try again, which temporarily disrupted the conversation flow.
   - **Valid Failure:** ✓ **YES** - This is a legitimate error where the agent failed to respond properly mid-conversation.

3. **Correct laptop options for user location** (score: 0.000)
   - **Failure Summary:** The agent failed to present the available laptop options for LATAM and instead provided information about the user's current laptop (ThinkPad X1 Carbon), which is **NOT** one of the options listed for LATAM.
   - **Valid Failure:** ✓ **YES** - The ThinkPad X1 Carbon is not in the LATAM laptop offerings. The valid LATAM options are:
     - MacBook Air M2
     - MacBook Pro 14 M3
     - ThinkPad T14 Gen 4 Intel
     - ThinkPad P16s Gen 2

#### Conversation Summary:
User requested laptop refresh → Agent confirmed eligibility → Agent had technical error ("difficulty generating a response") → Agent failed to list laptop options → User selected ThinkPad X1 Carbon (invalid for LATAM) → Ticket created (REQ5051984)

---

### Failure 3: generated_flow_worker0_7_20251212_045452.json

**File Path:** `/home/midawson/newpull/self-service-agent-blueprint/nightly_test_results/run_20156469756/results/conversation_results/generated_flow_worker0_7_20251212_045452.json`

**User:** maria.garcia@company.com (LATAM region)

**Metrics:** 12/15 passed

#### Failed Metrics:

1. **Option Presentation** (score: 0.600)
   - **Failure Summary:** The assistant failed to present appropriate laptop options based on the user's location and instead asked the user to specify a model without providing a list of options, which hindered the selection process.
   - **Valid Failure:** ✓ **YES** - Agent should have presented the LATAM laptop options.

2. **No errors reported by agent** (score: 0.800)
   - **Failure Summary:** The assistant apologized for having difficulty generating a response and asked the user to try again, which temporarily disrupted the conversation flow.
   - **Valid Failure:** ✓ **YES** - This is a legitimate error where the agent failed to respond properly mid-conversation.

3. **Correct laptop options for user location** (score: 0.000)
   - **Failure Summary:** The agent failed to present the available laptop options for LATAM and instead provided information about the user's current laptop (ThinkPad X1 Carbon), which is **NOT** one of the options listed for LATAM.
   - **Valid Failure:** ✓ **YES** - The ThinkPad X1 Carbon is not in the LATAM laptop offerings. The valid LATAM options are:
     - MacBook Air M2
     - MacBook Pro 14 M3
     - ThinkPad T14 Gen 4 Intel
     - ThinkPad P16s Gen 2

#### Conversation Summary:
User requested laptop refresh → Agent confirmed eligibility → Agent had technical error ("difficulty generating a response") → Agent failed to list laptop options → User selected ThinkPad X1 Carbon (invalid for LATAM) → Ticket created (REQ5489427)

---

## Common Pattern Across All Failures

All three failures exhibit the **same root issue**:

1. After confirming laptop refresh eligibility, the agent encounters a **technical error** ("I apologize, but I'm having difficulty generating a response right now. Please try again.")

2. The agent **fails to present location-specific laptop options** to the user

3. Users end up selecting laptops that are **not available in their region**:
   - APAC user selected: ZenBook Pro 15 (not in APAC offerings)
   - LATAM users selected: ThinkPad X1 Carbon (not in LATAM offerings)

4. All conversations still successfully created ServiceNow tickets, but with incorrect laptop selections

**All failures are valid** - the agent is not properly retrieving and presenting the correct laptop options for the user's location after experiencing a technical error in generating responses.
```

