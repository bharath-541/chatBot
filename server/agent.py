from typing import TypedDict, Annotated, Sequence
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
import operator
from db_service import DatabaseService
from tools import ToolRegistry
import logging
import json

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    session_id: str
    user_context: dict
    tool_calls: list
    intent: str  # "tool_required", "simple_chat", or "unknown"
    tools_executed: bool  # Track if tools have been executed
    system_memory: str  # Canonical memory block for LLM calls

class ChatAgent:
    def __init__(self, api_key: str, db_service: DatabaseService, tool_registry: ToolRegistry):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=api_key,
            temperature=0.7
        )
        self.db_service = db_service
        self.tool_registry = tool_registry
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the Langraph workflow with explicit intent routing"""
        workflow = StateGraph(AgentState)
        
        # Define nodes
        workflow.add_node("load_memory", self._load_memory)
        workflow.add_node("intent_router", self._route_intent)
        workflow.add_node("tool_node", self._execute_tools)
        workflow.add_node("llm_node", self._generate_response)
        workflow.add_node("save_memory", self._save_memory)
        
        # Define edges - explicit orchestration flow
        workflow.set_entry_point("load_memory")
        workflow.add_edge("load_memory", "intent_router")
        
        # Router always goes to LLM (it adds context but doesn't bypass LLM)
        workflow.add_edge("intent_router", "llm_node")
        
        # After LLM, check if it requested tools
        workflow.add_conditional_edges(
            "llm_node",
            self._check_tool_requests,
            {
                "execute_tools": "tool_node",
                "done": "save_memory"
            }
        )
        
        # After tools, go back to LLM to formulate response with tool results
        workflow.add_edge("tool_node", "llm_node")
        workflow.add_edge("save_memory", END)
        
        return workflow.compile()
    
    def _load_memory(self, state: AgentState) -> AgentState:
        """Load user memory from database"""
        session_id = state["session_id"]
        
        # Load recent conversations (short-term memory)
        recent_convs = self.db_service.get_recent_conversations(session_id, limit=10)
        
        # Load episodic memories
        episodic = self.db_service.get_episodic_memories(session_id, limit=3)
        
        # Load long-term memories
        long_term = self.db_service.get_all_long_term_memories(session_id)
        
        # Build canonical memory block (ALWAYS included in LLM calls)
        memory_parts = ["=== USER MEMORY ==="]
        
        if long_term:
            memory_parts.append("\nLONG-TERM FACTS:")
            for key, value in long_term.items():
                memory_parts.append(f"  {key}: {value}")
        
        if episodic:
            memory_parts.append("\nEPISODIC SUMMARY:")
            for ep in episodic:
                memory_parts.append(f"  - {ep.summary}")
        
        if recent_convs:
            memory_parts.append("\nRECENT CONVERSATION:")
            for conv in reversed(recent_convs[-6:]):  # Last 3 exchanges
                memory_parts.append(f"  {conv.role}: {conv.content[:100]}")
        
        memory_parts.append("\n===================\n")
        
        # Store canonical memory in state (persists across all LLM calls)
        state["system_memory"] = "\n".join(memory_parts)
        
        state["user_context"] = {
            "long_term": long_term,
            "episodic_count": len(episodic),
            "conversation_count": len(recent_convs)
        }
        
        logger.info(f"Loaded memory for session {session_id}: {len(long_term)} facts, {len(episodic)} episodes, {len(recent_convs)} conversations")
        return state
    
    def _route_intent(self, state: AgentState) -> AgentState:
        """Router node: Analyze user intent to decide next step"""
        user_message = state["messages"][-1].content.lower()
        
        # Simple intent detection (can be enhanced with ML)
        tool_keywords = {
            "hospital": "tool_required",
            "hospitals": "tool_required",
            "medical": "tool_required",
            "clinic": "tool_required",
            "doctor": "tool_required",
            "emergency": "tool_required",
            "find nearby": "tool_required",
            "search for": "tool_required"
        }
        
        # Check for tool-triggering keywords
        for keyword, intent in tool_keywords.items():
            if keyword in user_message:
                state["intent"] = intent
                logger.info(f"Router decision: {intent} (detected keyword: '{keyword}')")
                return state
        
        # Default: needs LLM to understand
        state["intent"] = "needs_llm_first"
        logger.info(f"Router decision: needs_llm_first")
        return state
    
    def _decide_next_step(self, state: AgentState) -> str:
        """Decision function for router"""
        intent = state.get("intent", "needs_llm_first")
        return intent if intent in ["tool_required", "needs_llm_first", "simple_chat"] else "needs_llm_first"
    
    def _check_tool_requests(self, state: AgentState) -> str:
        """Check if LLM response contains tool requests"""
        # If tools were already executed, don't execute again
        if state.get("tools_executed"):
            return "done"
        if state.get("tool_calls"):
            return "execute_tools"
        return "done"
    
    def _generate_response(self, state: AgentState) -> AgentState:
        """Generate AI response using Gemini"""
        # Check if tools have been executed
        tools_executed = state.get("tools_executed", False)
        messages = []  # Initialize messages list before if/else blocks
        
        if not tools_executed:
            # First LLM call - Use proper SystemMessage + HumanMessage structure
            system_parts = [
                "You are a helpful, friendly AI assistant.",
                "You can answer questions on any topic, have conversations, and help users with their tasks.",
                "Be conversational, helpful, and accurate. If you don't know something, say so."
            ]

            if state.get("system_memory"):
                system_parts.append(f"\n{state['system_memory']}")

            # Add tool descriptions
            tool_descriptions = self.tool_registry.get_tool_descriptions()
            if tool_descriptions:
                system_parts.append("\nAvailable tools:")
                for tool in tool_descriptions:
                    system_parts.append(f"- {tool['name']}: {tool['description']}")
                system_parts.append("\nIf you need to use a tool, respond with JSON: {\"tool\": \"tool_name\", \"params\": {...}}")
                system_parts.append("Otherwise, respond normally to help the user.")

            messages.append(SystemMessage(content="\n".join(system_parts)))
            messages.append(HumanMessage(content=state["messages"][-1].content if state["messages"] else "Hello"))
        else:
            # Second LLM call - Merge memory and results into one HumanMessage block
            prompt_parts = [
                "You are a helpful assistant.",
                "Use the TOOL RESULTS below to answer the user's question clearly.",
                "Format the response in natural language with bullet points.",
                "Do NOT mention JSON or internal tools to the user."
            ]

            if state.get("system_memory"):
                prompt_parts.append("\n=== USER MEMORY ===")
                prompt_parts.append(state["system_memory"])
            
            # Add tool results
            for msg in state["messages"]:
                if "Tool results" in msg.content:
                    prompt_parts.append("\n=== TOOL RESULTS ===")
                    prompt_parts.append(msg.content)
                    break
            
            # Add original user query
            for msg in state["messages"]:
                if isinstance(msg, HumanMessage):
                    prompt_parts.append("\n=== ORIGINAL USER QUERY ===")
                    # Strip tool descriptions if any
                    query = msg.content.split("\n\nAvailable tools:")[0].split("\n=== USER MESSAGE ===")[-1].strip()
                    prompt_parts.append(query)
                    break

            messages.append(HumanMessage(content="\n".join(prompt_parts)))
        
        response = self.llm.invoke(messages)
        
        # Check if response contains tool call (only if tools not executed yet)
        tool_calls = []
        if not tools_executed:
            try:
                content = response.content
                if "{" in content and "tool" in content:
                    # Try to extract JSON
                    start = content.find("{")
                    end = content.rfind("}") + 1
                    if start != -1 and end > start:
                        tool_json = json.loads(content[start:end])
                        if "tool" in tool_json:
                            tool_calls.append(tool_json)
            except:
                pass
        
        # Add AI response to state messages (only if not empty and not JSON)
        content = response.content.strip()
        if content and not (content.startswith("{") and "tool" in content):
            new_messages = [AIMessage(content=response.content)]
            state["messages"] = state["messages"] + new_messages
        elif not content:
            logger.warning(f"Empty response generated for session {state['session_id']}")
        
        state["tool_calls"] = tool_calls
        
        logger.info(f"Generated response for session {state['session_id']}, content length: {len(response.content)}, is_json: {content.startswith('{') if content else False}")
        return state
    
    def _should_execute_tools(self, state: AgentState) -> str:
        """Decide if tools should be executed"""
        if state.get("tool_calls"):
            return "tools"
        return "end"
    
    async def _execute_tools(self, state: AgentState) -> AgentState:
        """Execute any requested tools"""
        tool_results = []
        
        for tool_call in state.get("tool_calls", []):
            tool_name = tool_call.get("tool")
            params = tool_call.get("params", {})
            
            tool = self.tool_registry.get_tool(tool_name)
            if tool:
                logger.info(f"🔧 TOOL EXECUTION: {tool_name} with params: {params}")
                result = await tool.execute(**params)
                logger.info(f"✅ TOOL RESULT: Success={result.get('success')}, Count={result.get('count')} hospitals")
                tool_results.append({"tool": tool_name, "result": result})
            else:
                logger.warning(f"Tool not found: {tool_name}")
        
        if tool_results:
            tool_msg = SystemMessage(content=f"Tool results: {json.dumps(tool_results)}")
            state["messages"] = state["messages"] + [tool_msg]
        
        # Mark tools as executed and clear tool_calls to prevent loop
        state["tools_executed"] = True
        state["tool_calls"] = []
        
        return state
    
    def _save_memory(self, state: AgentState) -> AgentState:
        """Save conversation to database"""
        session_id = state["session_id"]
        messages = state["messages"]
        
        # Save the latest user and assistant messages
        for msg in messages[-2:]:  # Last 2 messages
            if isinstance(msg, HumanMessage):
                self.db_service.add_conversation(session_id, "user", msg.content)
            elif isinstance(msg, AIMessage):
                self.db_service.add_conversation(session_id, "assistant", msg.content)
        
        # Check if we should create an episodic memory
        conv_count = len(self.db_service.get_recent_conversations(session_id, limit=100))
        if conv_count > 0 and conv_count % 10 == 0:
            # Create summary every 10 messages
            recent = self.db_service.get_recent_conversations(session_id, limit=10)
            summary_text = f"Summary of {len(recent)} messages exchanged"
            self.db_service.create_episodic_memory(session_id, summary_text, len(recent))
            logger.info(f"Created episodic memory for session {session_id}")
        
        logger.info(f"Saved memory for session {session_id}")
        return state
    
    async def chat(self, message: str, session_id: str) -> str:
        """Main chat interface"""
        initial_state = {
            "messages": [HumanMessage(content=message)],
            "session_id": session_id,
            "user_context": {},
            "tool_calls": [],
            "tools_executed": False,
            "system_memory": ""  # Will be populated by _load_memory
        }
        
        result = await self.graph.ainvoke(initial_state)
        
        # Debug: log all messages
        logger.info(f"Final state has {len(result['messages'])} messages")
        for i, msg in enumerate(result["messages"]):
            logger.info(f"Message {i}: {type(msg).__name__} - {msg.content[:100] if len(msg.content) > 100 else msg.content}")
        
        # Extract final AI message
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage):
                logger.info(f"Returning AI message: {msg.content[:200]}")
                return msg.content
        
        return "I'm sorry, I couldn't generate a response."
