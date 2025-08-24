import uuid

class SessionManager:
    def __init__(self, agent_manager, available_agents):
        """
        Initializes the SessionManager.

        Args:
            agent_manager: An initialized AgentManager instance.
            available_agents: A dictionary of available agents.
        """
        self.agent_manager = agent_manager
        self.available_agents = available_agents
        self.user_sessions = {}

    def _generate_session_name(self, user_id: str, agent_name: str = None) -> str:
        """Generate a unique session name"""
        unique_id = str(uuid.uuid4())[:8]  # First 8 characters of UUID

        if agent_name:
            return f"slack-session-{user_id}-{agent_name}-{unique_id}"
        else:
            return f"slack-session-{user_id}-{unique_id}"

    def send_message_to_agent(
        self, agent_id: str, session_id: str, message: str
    ) -> str:
        """Send a message to an agent and return the response"""
        try:
            response_stream = self.agent_manager._client.agents.turn.create(
                agent_id=agent_id,
                session_id=session_id,
                stream=True,
                messages=[{"role": "user", "content": message}],
            )

            response = ""
            for chunk in response_stream:
                if hasattr(chunk, "error") and chunk.error:
                    error_message = chunk.error.get("message", "Unknown agent error")
                    print(f"Error from agent API: {error_message}")
                    return f"Error from agent: {error_message}"

                if (
                    hasattr(chunk, "event")
                    and hasattr(chunk.event, "payload")
                    and chunk.event.payload.event_type == "turn_complete"
                ):
                    if hasattr(chunk.event.payload.turn, "output_message"):
                        content = chunk.event.payload.turn.output_message.content
                        response += content

            return response.strip()

        except Exception as e:
            print(f"Error in send_message_to_agent: {e}")
            return f"Error: {str(e)}"

    def handle_user_message(
        self, user_id: str, text: str, user_email: str = None
    ) -> str:
        """
        Handles an incoming message, manages sessions and history, and returns a response.
        """
        if user_id not in self.user_sessions:
            routing_agent_id = self.available_agents.get("routing-agent")
            if not routing_agent_id:
                return "Error: Core routing agent not available."

            session_name = self._generate_session_name(user_id)
            session = self.agent_manager._client.agents.session.create(
                routing_agent_id, session_name=session_name
            )
            self.user_sessions[user_id] = {
                "agent_id": routing_agent_id,
                "session_id": session.session_id,
                "email": user_email,
            }
            print(f"New session for user {user_id} ({user_email})")

        current_session = self.user_sessions[user_id]

        # If we are already with a specialist agent, continue the conversation
        if current_session["agent_id"] != self.available_agents.get("routing-agent"):
            agent_response = self.send_message_to_agent(
                current_session["agent_id"],
                current_session["session_id"],
                text,
            )

            if agent_response.strip() == "ROUTING_AGENT_SESSION_DONE":
                print(f"Specialist agent finished. Resetting session for user {user_id}.")
                current_session["agent_id"] = self.available_agents.get("routing-agent")
                return "How can I help you next?"
        
        # Otherwise, we are with the routing agent
        else:
            agent_response = self.send_message_to_agent(
                current_session["agent_id"],
                current_session["session_id"],
                text,
            )

            potential_agent_name = agent_response.strip()
            if (
                potential_agent_name in self.available_agents
                and potential_agent_name != "routing-agent"
            ):
                print(f"Routing to agent: {potential_agent_name}")
                new_agent_id = self.available_agents[potential_agent_name]
                
                # Create a new session for the specialist agent
                session_name = self._generate_session_name(user_id, potential_agent_name)
                new_session = self.agent_manager._client.agents.session.create(
                    new_agent_id, session_name=session_name
                )
                
                # Update the current session to the new specialist agent
                current_session["agent_id"] = new_agent_id
                current_session["session_id"] = new_session.session_id
                
                # Send the message to the new agent
                agent_response = self.send_message_to_agent(
                    new_agent_id, current_session["session_id"], text
                )

        return agent_response