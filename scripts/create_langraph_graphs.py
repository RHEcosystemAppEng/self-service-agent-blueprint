#!/usr/bin/env python3
"""
Generate LangGraph visualizations for all prompt configurations.

This script uses the actual ConversationSession code to create graphs, ensuring
the visualizations match exactly what runs in production.

Requirements:
- npx (for mermaid-cli PNG generation, optional - will generate .md files without it)
- Must be run from the agent-service directory using uv (requires agent-service dependencies)

Usage:
    cd agent-service && uv run python ../scripts/create_langraph_graphs.py

Or use the make target:
    make generate-lg-diagrams
"""

import sys
from pathlib import Path
from typing import Any

# Add agent-service to path
repo_root = Path(__file__).parent.parent
agent_service_path = repo_root / "agent-service" / "src"
sys.path.insert(0, str(agent_service_path))

# Import the actual ConversationSession code
from agent_service.langgraph.lg_flow_state_machine import StateMachine  # noqa: E402


def create_graph_from_config(config_path: Path) -> Any:
    """
    Create a LangGraph workflow using the actual StateMachine class.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        Compiled LangGraph application
    """
    # Create a StateMachine with the config
    state_machine = StateMachine(str(config_path))

    # Create the graph using StateMachine's logic
    # We need to replicate what ConversationSession._create_graph() does
    from langgraph.graph import END, StateGraph
    from langgraph.types import Command

    workflow = StateGraph(state_machine.AgentState)  # type: ignore[type-var]

    # Get configuration
    states_config = state_machine.config.get("states", {})
    settings = state_machine.config.get("settings", {})
    initial_state = settings.get("initial_state", "start")

    # Add nodes - simplified version for visualization
    for state_name, state_config in states_config.items():
        state_type = state_config.get("type", "")

        # Create a simple node function for visualization
        def make_node_func(name: str, stype: str) -> Any:
            def node_func(state: dict[str, Any]) -> dict[str, Any] | Command[Any]:
                """Simplified node for visualization."""
                if stype == "terminal":
                    return state
                # For visualization, just return a command to show transitions
                return Command(goto="next", update={"current_state": name})

            return node_func

        workflow.add_node(state_name, make_node_func(state_name, state_type))

    # Set entry point
    workflow.set_entry_point(initial_state)

    # Add edges based on ALL possible transitions from YAML
    # The actual runtime uses Command(goto=X) for dynamic routing,
    # but for visualization we need explicit edges to show all paths
    for state_name, state_config in states_config.items():
        state_type = state_config.get("type", "")

        # Terminal states always go to END
        if state_type == "terminal":
            workflow.add_edge(state_name, END)
            continue

        # Collect all possible transition targets from multiple sources
        all_targets = []

        # 1. From 'transitions' field (waiting states, simple transitions)
        transitions = state_config.get("transitions", {})
        for key, target in transitions.items():
            if target:
                all_targets.append((key, target))

        # 2. From 'response_analysis' conditions (LLM processor states)
        response_analysis = state_config.get("response_analysis", {})

        # Check each condition for transition actions
        for condition in response_analysis.get("conditions", []):
            condition_name = condition.get("name", "condition")
            for action in condition.get("actions", []):
                if action.get("type") == "transition":
                    target = action.get("target")
                    if target:
                        all_targets.append((condition_name, target))

        # Check default_transition
        default_transition = response_analysis.get("default_transition")
        if default_transition:
            all_targets.append(("default", default_transition))

        # 3. From 'intent_actions' field (intent_classifier states)
        intent_actions = state_config.get("intent_actions", {})
        for intent_name, intent_config in intent_actions.items():
            next_state = intent_config.get("next_state")
            if next_state:
                all_targets.append((intent_name, next_state))

        # Keep all targets - don't deduplicate even if same target
        # We want to show all possible conditions that lead to each target
        unique_targets = all_targets

        # Add edges based on collected targets
        if not unique_targets:
            # No transitions defined - shouldn't happen but handle it
            continue

        if len(unique_targets) == 1:
            # Single target - use regular edge
            _, target = unique_targets[0]
            if target == "end":
                workflow.add_edge(state_name, END)
            else:
                workflow.add_edge(state_name, target)
        else:
            # Multiple targets - use conditional edges to show all paths
            def make_router(targets: list[tuple[str, str]]) -> Any:
                def route_func(state: dict[str, Any]) -> str:
                    # For visualization, return first target
                    return targets[0][1] if targets else "end"

                return route_func

            # Create edge mapping with condition labels
            edge_mapping = {}
            for label, target in unique_targets:
                if target == "end":
                    edge_mapping[label] = END
                else:
                    edge_mapping[label] = target

            workflow.add_conditional_edges(
                state_name, make_router(unique_targets), edge_mapping
            )

    # Compile
    return workflow.compile()


def add_missing_transitions(mermaid_syntax: str, config: dict[str, Any]) -> str:
    """
    Add missing transitions to Mermaid diagram that LangGraph deduplicated.

    LangGraph only shows one edge per unique target in conditional_edges,
    but we want to show all possible condition paths.
    """
    states_config = config.get("states", {})
    additional_edges = []

    for state_name, state_config in states_config.items():
        # Collect all transitions from this state
        all_transitions = []

        # From transitions field
        transitions = state_config.get("transitions", {})
        for key, target in transitions.items():
            if target:
                all_transitions.append((key, target))

        # From response_analysis conditions
        response_analysis = state_config.get("response_analysis", {})
        for condition in response_analysis.get("conditions", []):
            condition_name = condition.get("name", "condition")
            for action in condition.get("actions", []):
                if action.get("type") == "transition":
                    target = action.get("target")
                    if target:
                        all_transitions.append((condition_name, target))

        # From default_transition
        default = response_analysis.get("default_transition")
        if default:
            all_transitions.append(("default", default))

        # From intent_actions (intent_classifier states)
        intent_actions = state_config.get("intent_actions", {})
        for intent_name, intent_config in intent_actions.items():
            next_state = intent_config.get("next_state")
            if next_state:
                all_transitions.append((intent_name, next_state))

        # Group by target to see which have multiple conditions
        target_conditions = {}
        for label, target in all_transitions:
            if target not in target_conditions:
                target_conditions[target] = []
            target_conditions[target].append(label)

        # For targets with multiple conditions, add edges for the missing ones
        for target, labels in target_conditions.items():
            if len(labels) > 1:
                # Multiple conditions lead to this target
                # LangGraph only shows one, so add the others
                target_node = "__end__" if target == "end" else target

                for label in labels:
                    # Check if this edge exists
                    edge_pattern = (
                        f"{state_name} -. &nbsp;{label}&nbsp; .-> {target_node};"
                    )
                    if edge_pattern not in mermaid_syntax:
                        # Edge is missing, add it
                        additional_edges.append(edge_pattern)

    # Add the missing edges to the Mermaid syntax
    if additional_edges:
        # Find where to insert (before classDef lines)
        lines = mermaid_syntax.split("\n")
        insert_index = None
        for i, line in enumerate(lines):
            if line.strip().startswith("classDef"):
                insert_index = i
                break

        if insert_index is not None:
            # Insert additional edges before classDef
            for edge in additional_edges:
                lines.insert(insert_index, "\t" + edge)
                insert_index += 1
            mermaid_syntax = "\n".join(lines)

    return mermaid_syntax


def generate_visualizations(prompts_dir: Path, output_dir: Path) -> None:
    """
    Generate visualizations for all YAML prompt configurations.

    Outputs both Mermaid markdown (.md) and PNG files (.png) when possible.

    Args:
        prompts_dir: Directory containing YAML prompt files
        output_dir: Directory to save outputs
    """
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all YAML files
    yaml_files = sorted(prompts_dir.glob("*.yaml"))

    if not yaml_files:
        print(f"No YAML files found in {prompts_dir}")
        return

    print(f"Found {len(yaml_files)} prompt configuration files")
    print("=" * 70)

    mermaid_count = 0
    success_count = 0

    for yaml_file in yaml_files:
        print(f"\nProcessing: {yaml_file.name}")

        try:
            # Create StateMachine to get config and graph
            import yaml as yaml_lib

            with open(yaml_file, "r") as f:
                config = yaml_lib.safe_load(f)

            # Create graph using actual StateMachine code
            app = create_graph_from_config(yaml_file)

            # Get graph representation
            graph = app.get_graph()

            # Generate output filename
            mermaid_output = output_dir / f"{yaml_file.stem}-diagram.md"

            # Generate Mermaid markdown file
            mermaid_syntax = graph.draw_mermaid()

            # Fix reserved keyword issue: 'end' is a reserved keyword in Mermaid
            # LangGraph sometimes generates end(end) which is invalid
            # Replace it with __end__ (LangGraph's built-in terminal node) instead of creating a separate node
            mermaid_syntax = mermaid_syntax.replace("end(end)", "__end__")
            mermaid_syntax = mermaid_syntax.replace(" --> end;", " --> __end__;")
            mermaid_syntax = mermaid_syntax.replace(" .-> end;", " .-> __end__;")

            # LangGraph deduplicates edges by target in visualizations
            # Manually add missing edges by parsing the YAML
            mermaid_syntax = add_missing_transitions(mermaid_syntax, config)

            with open(mermaid_output, "w") as f:
                f.write("```mermaid\n")
                f.write(mermaid_syntax)
                f.write("\n```\n")
            print(f"  ✓ Generated Mermaid: {mermaid_output.relative_to(repo_root)}")
            mermaid_count += 1

            # Try to generate PNG using mermaid-cli if npx is available
            import shutil
            import subprocess

            png_output = output_dir / f"{yaml_file.stem}-diagram.png"

            if shutil.which("npx"):
                try:
                    # Use mermaid-cli to convert markdown to PNG with high resolution
                    # -s 3: 3x scale factor for higher resolution
                    # -w 2400: wider page to accommodate complex graphs
                    result = subprocess.run(
                        [
                            "npx",
                            "-y",
                            "@mermaid-js/mermaid-cli",
                            "-i",
                            str(mermaid_output),
                            "-o",
                            str(png_output),
                            "-s",
                            "3",  # 3x scale for high resolution
                            "-w",
                            "2400",  # Wider page
                            "-b",
                            "white",  # White background
                        ],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )

                    # mermaid-cli adds "-1" suffix to output files
                    actual_png = output_dir / f"{yaml_file.stem}-diagram-1.png"

                    if result.returncode == 0 and actual_png.exists():
                        # Rename to remove the -1 suffix
                        actual_png.rename(png_output)
                        print(f"  ✓ Generated PNG: {png_output.relative_to(repo_root)}")
                        success_count += 1
                    elif png_output.exists():
                        print(f"  ✓ Generated PNG: {png_output.relative_to(repo_root)}")
                        success_count += 1
                    else:
                        if result.stderr:
                            print(f"  ⚠ PNG generation failed: {result.stderr[:100]}")
                        else:
                            print(
                                "  ⚠ PNG generation failed (Mermaid markdown available)"
                            )
                except Exception as e:
                    print(f"  ⚠ PNG generation skipped: {e}")
            else:
                print("  ⚠ PNG skipped (npx not available)")

        except Exception as e:
            print(f"  ✗ Error: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 70)
    print("Visualization generation complete!")
    print(f"  Mermaid diagrams: {mermaid_count}/{len(yaml_files)}")
    print(f"  PNG images: {success_count}/{len(yaml_files)}")
    print(f"  Output directory: {output_dir.relative_to(repo_root)}")

    if success_count < mermaid_count:
        print()
        print("To manually render remaining PNG images:")
        print("  1. https://mermaid.live (paste the .md file contents)")
        print("  2. GitHub/GitLab (renders Mermaid natively in markdown)")
        print("  3. VS Code with Mermaid Preview extension")
        print("  4. Install npx: npm install -g npx (if not available)")


def main() -> None:
    """Main entry point."""
    # Define paths
    prompts_dir = repo_root / "agent-service" / "config" / "lg-prompts"
    output_dir = repo_root / "docs" / "images"

    print("LangGraph Visualization Generator")
    print("=" * 70)
    print(f"Repository root: {repo_root}")
    print(f"Prompts directory: {prompts_dir}")
    print(f"Output directory: {output_dir}")
    print()

    # Check if prompts directory exists
    if not prompts_dir.exists():
        print(f"Error: Prompts directory not found: {prompts_dir}")
        sys.exit(1)

    # Generate visualizations
    generate_visualizations(prompts_dir, output_dir)


if __name__ == "__main__":
    main()
