import streamlit as st
import requests
import json
from datetime import datetime, timezone
import uuid

# Backend API URL
API_URL = ( "https://chatbot-0y4t.onrender.com")
# Version: 1.0.1 - Fixed timezone display

# Initialize session state
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "user_profile" not in st.session_state:
    st.session_state.user_profile = {"name": None, "email": None}
if "session_name" not in st.session_state:
    st.session_state.session_name = ""

# Page config
st.set_page_config(
    page_title="Chatbot",
    page_icon="💬",
    layout="wide"
)

# Sidebar
with st.sidebar:
    st.title("Chat")
    
    # Session controls
    col1, col2 = st.columns(2)
    with col1:
        if st.button("New", use_container_width=True):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.session_state.session_name = ""
            st.rerun()
    
    with col2:
        if st.button("Clear", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
    
    # Session naming
    session_display = st.session_state.session_name if st.session_state.session_name else f"{st.session_state.session_id[:8]}..."
    new_name = st.text_input("Session Name", value=st.session_state.session_name, placeholder="Name this session...", label_visibility="collapsed")
    if new_name != st.session_state.session_name:
        st.session_state.session_name = new_name
        # Save to database
        try:
            requests.put(
                f"{API_URL}/user/profile/{st.session_state.session_id}",
                json={"name": new_name, "email": ""}
            )
        except:
            pass
        st.rerun()
    
    st.divider()
    
    # Past Sessions - Ultra compact dropdown
    try:
        response = requests.get(f"{API_URL}/sessions", timeout=5)
        if response.status_code == 200:
            data = response.json()
            # Filter sessions with messages
            sessions = [s for s in data.get("sessions", [])[:20] if s.get("message_count", 0) > 0]
            
            if len(sessions) > 1:  # Only show if there are multiple sessions
                session_options = []
                session_map = {}
                
                for session in sessions:
                    session_id = session["session_id"]
                    msg_count = session.get("message_count", 0)
                    
                    # Create display name
                    if session.get("name"):
                        display = f"{session['name']} ({msg_count} msgs)"
                    else:
                        display = f"{session_id[:8]}... ({msg_count} msgs)"
                    
                    session_options.append(display)
                    session_map[display] = session_id
                
                # Find current session in options
                current_idx = 0
                for i, (opt, sid) in enumerate(session_map.items()):
                    if sid == st.session_state.session_id:
                        current_idx = i
                        break
                
                # Callback function to load session
                def load_session():
                    selected = st.session_state.session_selector
                    selected_id = session_map[selected]
                    
                    if selected_id != st.session_state.session_id:
                        st.session_state.session_id = selected_id
                        
                        # Find session name
                        for s in sessions:
                            if s["session_id"] == selected_id:
                                st.session_state.session_name = s.get("name") or ""
                                break
                        
                        # Load conversation history
                        try:
                            conv_response = requests.get(f"{API_URL}/conversations/{selected_id}")
                            if conv_response.status_code == 200:
                                conv_data = conv_response.json()
                                st.session_state.messages = [
                                    {"role": conv["role"], "content": conv["content"], "timestamp": conv.get("timestamp")}
                                    for conv in reversed(conv_data["conversations"])
                                ]
                        except:
                            st.session_state.messages = []
                
                # Dropdown selector
                st.caption("Switch session:")
                st.selectbox(
                    "Past Sessions",
                    options=session_options,
                    index=current_idx,
                    label_visibility="collapsed",
                    key="session_selector",
                    on_change=load_session
                )
    except Exception as e:
        pass

# Main chat interface
st.title("Chatbot")
session_title = st.session_state.session_name if st.session_state.session_name else "Current Session"
st.caption(f"**{session_title}**")

# Show message count if any messages exist
if st.session_state.messages:
    st.caption(f"{len(st.session_state.messages)} messages in this conversation")

# Display chat messages with timestamps
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.write(message["content"])
        # Show timestamp if available
        if "timestamp" in message and message["timestamp"]:
            try:
                # Parse timestamp and convert to local time
                ts_str = message["timestamp"]
                
                # Handle different timestamp formats
                if ts_str.endswith('Z'):
                    # Old format: "2026-01-01T10:41:00.123456Z"
                    ts = datetime.fromisoformat(ts_str[:-1]).replace(tzinfo=timezone.utc)
                elif '+' in ts_str:
                    # New format: "2026-01-01T10:41:00.123456+00:00"
                    ts = datetime.fromisoformat(ts_str)
                else:
                    # No timezone info, assume UTC
                    ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
                
                # Convert to local timezone
                local_ts = ts.astimezone()
                st.caption(f"{local_ts.strftime('%b %d, %I:%M %p')}")
            except Exception as e:
                # Fallback: show raw timestamp
                st.caption(f"🕐 {message['timestamp'][:19]}")

# Chat input
if prompt := st.chat_input("Ask me anything..."):
    # Add user message to chat with timestamp
    st.session_state.messages.append({
        "role": "user", 
        "content": prompt,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    with st.chat_message("user"):
        st.write(prompt)
    
    # Get AI response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = requests.post(
                    f"{API_URL}/chat",
                    json={
                        "message": prompt,
                        "session_id": st.session_state.session_id
                    },
                    timeout=20
                )
                
                if response.status_code == 200:
                    data = response.json()
                    assistant_message = data["response"]
                    st.write(assistant_message)
                    
                    # Add to session with timestamp
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": assistant_message,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    
                    # Show response time if available
                    if "X-Process-Time" in response.headers:
                        st.caption(f"⚡ Response time: {response.headers['X-Process-Time']}")
                else:
                    st.error(f"Error: {response.status_code} - {response.text}")
            
            except requests.exceptions.Timeout:
                st.error("Request timed out (>20s). Please try again.")
            except Exception as e:
                st.error(f"Error connecting to backend: {e}")
                st.info("Make sure the backend server is running on http://localhost:8000")

# Footer
st.divider()
st.caption("""
**Features:** 
- Persistent memory (short-term, episodic, long-term)
- Tool integration (hospital search)
- Background task scheduling
- Performance profiling
- Conversation history
""")
