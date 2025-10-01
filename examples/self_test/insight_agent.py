"""
Clean OpenAI Agent with MCP, Sessions, and Hooks

Simple implementation that just works.
"""

import asyncio
import os
import sys
from pathlib import Path

# Handle imports for both direct execution and module import
if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent.parent
    src_dir = project_root / "src"
    sys.path.insert(0, str(src_dir))  # Use src directory where agents module is located
    print(f"Using local agents source from: {src_dir}")

from agents import Agent, Runner
from agents.tool import WebSearchTool
from agents.mcp import MCPServerStdio
from agents.lifecycle import RunHooks
from agents.memory import SQLiteSession

import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleHooks(RunHooks):
    """Simple hooks for debugging with error tracking"""
    
    def __init__(self):
        super().__init__()
        self.last_tool_error = None
        self.tool_errors = []
    
    async def on_tool_start(self, context, agent, tool):
        logger.info(f"🔧 TOOL START: {tool.name}")
    
    async def on_tool_end(self, context, agent, tool, result):
        # Check if result contains an error
        result_str = str(result)
        if "error" in result_str.lower() or "database configuration not set" in result_str.lower():
            error_info = {
                "tool": tool.name,
                "error": result_str[:500],
                "timestamp": "just now"
            }
            self.last_tool_error = error_info
            self.tool_errors.append(error_info)
            logger.error(f"❌ TOOL ERROR: {tool.name}")
            logger.error(f"   💥 Error: {result_str[:200]}")
        else:
            logger.info(f"✅ TOOL END: {tool.name} -> {str(result)[:100]}")


async def create_agent_and_servers():
    """Create agent with MCP servers and connect them"""
    # Check API key
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    mcp_servers = []
    
    # Graphiti Memory - fix the initialization
    try:
        graphiti_server = MCPServerStdio(
            params={
                "command": "npx",
                "args": ["mcp-remote", "http://localhost:8000/sse"],
            }
        )
        await graphiti_server.connect()
        mcp_servers.append(graphiti_server)
        logger.info("✅ Graphiti MCP server connected")
    except Exception as e:
        logger.warning(f"Failed to connect to Graphiti MCP server: {e}")
    
    # PostgreSQL - using the package that works locally
    try:
        postgres_env = os.environ.copy()
        postgres_env["DATABASE_URL"] = os.getenv("DATABASE_URL", "postgresql://admin:admin123@localhost:5432/mydb")
        
        postgres_server = MCPServerStdio(
            params={
                "command": "npx",
                "args": ["mcp-postgres-server"],
                "env": postgres_env
            }
        )
        await postgres_server.connect()
        mcp_servers.append(postgres_server)
        logger.info("✅ PostgreSQL MCP server connected")
    except Exception as e:
        logger.warning(f"Failed to connect to PostgreSQL MCP server: {e}")
    
    # Create agent
    agent = Agent(
        name="Insight Agent",
        instructions="""You are a helpful AI assistant with access to:
- Web search for current information  
- Graphiti memory for persistent knowledge storage
- PostgreSQL database for structured data

When you encounter tool errors:
- Read the error message carefully
- Always acknowledge errors explicitly in your responses
- When asked about errors, refer to the specific tool calls and their results""",
        tools=[WebSearchTool()],
        mcp_servers=mcp_servers,
    )
    
    logger.info(f"✅ Agent created with {len(mcp_servers)} MCP servers")
    return agent, mcp_servers


async def run_chat():
    """Run chat with session memory and hooks"""
    print("🤖 Clean OpenAI Agent with MCP Support")
    print("=" * 50)
    
    agent, mcp_servers = await create_agent_and_servers()
    session = SQLiteSession("chat_session")
    hooks = SimpleHooks()
    
    print("✅ Agent ready! Type 'quit' to exit")
    print("=" * 50)
    
    try:
        while True:
            user_input = input("\n💬 You: ").strip()
            
            if not user_input:
                continue
            
            # Debug command to inspect session
            if user_input.lower() == "debug session":
                items = await session.get_items()
                print(f"\n📊 Session has {len(items)} items:")
                for i, item in enumerate(items[-5:], 1):  # Show last 5
                    print(f"  {i}. {item.get('type', item.get('role', 'unknown'))}: {str(item)[:100]}")
                continue
                
            if user_input.lower() in ['quit', 'exit', 'bye']:
                print("👋 Goodbye!")
                break
            
            print("🤔 Thinking...")
            
            # Reset tool error tracking for this turn
            hooks.last_tool_error = None
            
            # Add context about previous tool errors if user is asking about errors
            enhanced_input = user_input
            if ("error" in user_input.lower() or "tool call" in user_input.lower()) and hooks.tool_errors:
                # Provide context about recent tool errors
                recent_errors = hooks.tool_errors[-3:]  # Last 3 errors
                error_context = "\n\n[System Note: Recent tool errors for context:\n"
                for i, err in enumerate(recent_errors, 1):
                    error_context += f"{i}. Tool '{err['tool']}' error: {err['error'][:200]}...\n"
                error_context += "]"
                enhanced_input = user_input + error_context
            
            try:
                result = await Runner.run(
                    agent, 
                    enhanced_input, 
                    session=session,
                    hooks=hooks,
                    max_turns=10
                )
                
                # Check if there was a tool error during this turn
                if hooks.last_tool_error:
                    error_msg = f"\n⚠️  Note: Tool '{hooks.last_tool_error['tool']}' encountered an error:\n{hooks.last_tool_error['error'][:300]}"
                    print(error_msg)
                
                print(f"\n🤖 Agent: {result.final_output}")
                
            except Exception as e:
                # Only catch non-tool errors (framework/system errors)
                # Tool errors should be handled by the agent itself
                if "MCP error" not in str(e):
                    logger.error(f"System error: {e}")
                    print(f"❌ System Error: {e}")
                else:
                    # This shouldn't happen - MCP tool errors should be returned as tool results
                    # not raised as exceptions
                    logger.error(f"MCP tool error raised as exception (should be tool result): {e}")
                    print(f"❌ Error: {e}")
                    print("⚠️  The agent should have been able to handle this automatically.")
    
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    
    finally:
        # Clean up MCP servers
        for server in mcp_servers:
            try:
                await server.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up server: {e}")


if __name__ == "__main__":
    asyncio.run(run_chat())