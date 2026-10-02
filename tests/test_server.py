from mcp.server import MCPServer

from continuity_mcp.server import mcp


def test_server_uses_current_mcp_v2_api():
    assert isinstance(mcp, MCPServer)
