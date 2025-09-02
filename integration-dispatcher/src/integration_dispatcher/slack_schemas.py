"""Slack event and interaction schemas."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SlackUser(BaseModel):
    """Slack user information."""

    id: str
    username: Optional[str] = None
    name: Optional[str] = None
    team_id: Optional[str] = None


class SlackChannel(BaseModel):
    """Slack channel information."""

    id: str
    name: Optional[str] = None


class SlackMessage(BaseModel):
    """Slack message event."""

    type: str
    subtype: Optional[str] = None
    text: str
    user: str
    ts: str
    channel: str
    channel_type: Optional[str] = None
    thread_ts: Optional[str] = None
    bot_id: Optional[str] = None


class SlackEvent(BaseModel):
    """Slack event wrapper."""

    type: str
    event: Dict[str, Any]
    team_id: str
    api_app_id: str
    event_id: str
    event_time: int
    authorizations: Optional[List[Dict[str, Any]]] = None
    is_ext_shared_channel: Optional[bool] = None
    event_context: Optional[str] = None


class SlackEventRequest(BaseModel):
    """Complete Slack event request."""

    token: str
    team_id: str
    api_app_id: str
    event: SlackEvent
    type: str
    event_id: str
    event_time: int
    authorizations: Optional[List[Dict[str, Any]]] = None
    is_ext_shared_channel: Optional[bool] = None
    event_context: Optional[str] = None


class SlackChallenge(BaseModel):
    """Slack URL verification challenge."""

    token: str
    challenge: str
    type: str


class SlackInteractionPayload(BaseModel):
    """Slack interaction payload."""

    type: str
    user: SlackUser
    api_app_id: str
    token: str
    container: Optional[Dict[str, Any]] = None
    trigger_id: Optional[str] = None
    team: Optional[Dict[str, str]] = None
    enterprise: Optional[Dict[str, str]] = None
    is_enterprise_install: Optional[bool] = None
    channel: Optional[SlackChannel] = None
    message: Optional[Dict[str, Any]] = None
    response_url: Optional[str] = None
    actions: Optional[List[Dict[str, Any]]] = None
    view: Optional[Dict[str, Any]] = None


class SlackSlashCommand(BaseModel):
    """Slack slash command payload."""

    token: str
    team_id: str
    team_domain: str
    channel_id: str
    channel_name: str
    user_id: str
    user_name: str
    command: str
    text: str
    response_url: str
    trigger_id: str
    api_app_id: str
