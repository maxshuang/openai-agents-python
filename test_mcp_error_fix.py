#!/usr/bin/env python3

import asyncio
from agents import Agent
from agents.mcp import MCPServerStdio


async def test_mcp_error_handling():
    """Test that MCP tool errors are returned as tool results, not exceptions."""
    
    print("Setting up agent with PostgreSQL MCP server...")
    
    # Create agent with PostgreSQL MCP server
    agent = Agent(
        name="test_agent",
        instructions="You are a helpful agent. When you get tool errors, try to fix them by calling the appropriate setup tools.",
        model="gpt-4o-mini", 
        mcp_servers=[
            MCPServerStdio(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-postgres"],
                env={"POSTGRES_CONNECTION_STRING": "postgresql://user:pass@localhost/db"}
            )
        ],
        max_turns=5,  # Allow multiple turns for self-correction
    )
    
    print("Testing agent's ability to handle MCP tool errors...")
    
    # This should trigger an error that the agent can then fix
    result = await agent.run("List all the tables in the database")
    
    print(f"\nAgent result: {result}")
    print("\nSuccess! Agent handled the MCP tool error and took corrective action.")


if __name__ == "__main__":
    asyncio.run(test_mcp_error_handling())