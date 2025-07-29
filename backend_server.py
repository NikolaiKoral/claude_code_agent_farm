#!/usr/bin/env python3
"""
FastAPI Backend Server for Business Analysis Agent Farm
Acts as a pure interface layer between Next.js frontend and existing business analysis farm
"""

import asyncio
import json
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import tempfile
import shutil
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from pydantic import BaseModel

# Import the existing business analysis farm (unchanged)
from business_analysis_farm import BusinessAnalysisFarm

# Import the new Claude SDK Agent Farm for streaming
from claude_sdk_agent_farm import ClaudeSDKAgentFarm, StreamingMessage

# ─────────────────────────────── Models ────────────────────────────── #

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    files: List[Dict[str, Any]] = []
    uploaded_file_paths: List[str] = []  # Add support for referencing uploaded files

class AnalysisRequest(BaseModel):
    config_name: str = "kop_kande_cc_fee_analysis"
    file_path: Optional[str] = None
    message: Optional[str] = None
    conversation_context: Optional[str] = None
    excel_files: List[str] = []
    agents: int = 10
    language: str = "danish"
    analysis_type: str = "business_case_development"
    business_context: Dict[str, Any] = {}

class SessionStatus(BaseModel):
    session_id: str
    status: str  # "starting", "running", "completed", "error"
    progress: int = 0
    agents_active: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    results_available: bool = False
    excel_files: List[str] = []
    message: str = ""

# ─────────────────────────────── Global State ────────────────────────────── #

app = FastAPI(title="Business Analysis Agent Farm API", version="1.0.0")

# CORS middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global session tracking
active_sessions: Dict[str, SessionStatus] = {}
websocket_connections: Dict[str, WebSocket] = {}

# Ensure uploads directory exists
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

# ─────────────────────────────── File Upload Handler ────────────────────────────── #

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Handle Excel file uploads from frontend"""
    try:
        # Validate file type
        if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
            raise HTTPException(status_code=400, detail="Only Excel and CSV files are supported")
        
        # Generate unique filename
        file_id = str(uuid.uuid4())
        filename = f"{file_id}_{file.filename}"
        file_path = UPLOADS_DIR / filename
        
        # Save uploaded file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return {
            "file_id": file_id,
            "filename": file.filename,
            "file_path": str(file_path),
            "size": file_path.stat().st_size,
            "uploaded_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

@app.get("/api/files")
async def list_uploaded_files():
    """List all uploaded files, deduplicated by original filename"""
    try:
        files = []
        seen_files = {}  # Track by original filename to avoid duplicates
        
        if UPLOADS_DIR.exists():
            for file_path in UPLOADS_DIR.glob("*"):
                if file_path.is_file() and file_path.suffix.lower() in ['.xlsx', '.xls', '.csv']:
                    # Extract original filename (everything after first underscore)
                    filename_parts = file_path.name.split('_', 1)
                    original_filename = filename_parts[1] if len(filename_parts) > 1 else file_path.name
                    
                    file_info = {
                        "filename": original_filename,
                        "path": str(file_path),
                        "size": file_path.stat().st_size,
                        "uploaded_at": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                    }
                    
                    # Keep only the most recent version of each file
                    if original_filename not in seen_files or file_path.stat().st_mtime > seen_files[original_filename]["mtime"]:
                        seen_files[original_filename] = {
                            **file_info,
                            "mtime": file_path.stat().st_mtime
                        }
            
            # Convert to list and remove mtime field
            files = [{k: v for k, v in file_info.items() if k != "mtime"} 
                    for file_info in seen_files.values()]
            
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")

# ─────────────────────────────── Configuration Management ────────────────────────────── #

@app.get("/api/configs")
async def get_configs():
    """Get available analysis configurations"""
    configs_dir = Path("configs")
    configs = []
    
    if configs_dir.exists():
        for config_file in configs_dir.glob("*.json"):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    configs.append({
                        "name": config_file.stem,
                        "display_name": config_data.get("display_name", config_file.stem),
                        "description": config_data.get("description", "Business analysis configuration"),
                        "file_path": str(config_file)
                    })
            except Exception:
                continue
    
    return configs

# ─────────────────────────────── Analysis Orchestration ────────────────────────────── #

@app.post("/api/analysis/start")
async def start_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """Start business analysis using Claude SDK streaming (with tmux fallback)"""
    session_id = str(uuid.uuid4())
    
    try:
        # Create session status
        session_status = SessionStatus(
            session_id=session_id,
            status="starting",
            start_time=datetime.now(),
            excel_files=request.excel_files,
            message="Initializing Claude SDK business analysis farm..."
        )
        active_sessions[session_id] = session_status
        
        # Try Claude SDK streaming first, fallback to tmux if needed
        background_tasks.add_task(run_claude_sdk_analysis, session_id, request)
        
        print(f"[DEBUG] Claude SDK analysis session {session_id} created")
        
        return {
            "session_id": session_id,
            "status": "starting",
            "message": "Claude SDK business analysis farm is starting..."
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start analysis: {str(e)}")

@app.post("/api/analysis/start-tmux")
async def start_tmux_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """Start business analysis using original tmux system (fallback)"""
    session_id = str(uuid.uuid4())
    
    try:
        # Create session status
        session_status = SessionStatus(
            session_id=session_id,
            status="starting",
            start_time=datetime.now(),
            excel_files=request.excel_files,
            message="Initializing tmux business analysis farm..."
        )
        active_sessions[session_id] = session_status
        
        # Schedule background analysis task
        background_tasks.add_task(run_analysis_farm, session_id, request)
        # Schedule progress monitoring task immediately 
        background_tasks.add_task(monitor_analysis_progress, session_id)
        
        print(f"[DEBUG] Tmux analysis session {session_id} created, monitoring scheduled")
        
        return {
            "session_id": session_id,
            "status": "starting",
            "message": "Tmux business analysis farm is starting..."
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start analysis: {str(e)}")

async def monitor_analysis_progress(session_id: str):
    """Monitor tmux session progress and stream agent thinking in real-time"""
    tmux_session = f"business_agents_{session_id[:8]}"
    
    print(f"[DEBUG] Starting monitoring for session {session_id} (tmux: {tmux_session})")
    
    # Wait a shorter time for session to start
    await asyncio.sleep(2)
    
    try:
        # Track last captured content for each agent to detect new output
        agent_last_content = {}
        
        while session_id in active_sessions:
            session = active_sessions[session_id]
            
            print(f"[DEBUG] Monitoring loop: session {session_id} status: {session.status}")
            
            # Monitor if session is starting or running
            if session.status not in ["starting", "running"]:
                await asyncio.sleep(3)
                continue
            
            # Check tmux session status and capture agent output
            result = subprocess.run(
                ["tmux", "list-windows", "-t", tmux_session], 
                capture_output=True, text=True, check=False
            )
            
            if result.returncode == 0:
                # Parse tmux windows to get agent information
                windows = result.stdout.strip().split('\n') if result.stdout.strip() else []
                agent_windows = [w for w in windows if 'agent_' in w]
                active_agents = len(agent_windows)
                
                # Update session status
                session.agents_active = active_agents
                session.message = f"Analysis running: {active_agents} agents active"
                
                # Stream content from each agent window
                for window_line in agent_windows:
                    # Extract window info (format: "1: agent_0_financial_modeling (1 panes) ...")
                    window_parts = window_line.split(':')
                    if len(window_parts) >= 2:
                        window_name = window_parts[1].strip().split(' ')[0]
                        
                        # Capture recent pane content (last 5 lines)
                        pane_target = f"{tmux_session}:{window_name}"
                        content_result = subprocess.run(
                            ["tmux", "capture-pane", "-t", pane_target, "-p", "-S", "-5"],
                            capture_output=True, text=True, check=False
                        )
                        
                        if content_result.returncode == 0:
                            current_content = content_result.stdout.strip()
                            
                            # Check if there's new content since last check
                            if window_name not in agent_last_content or agent_last_content[window_name] != current_content:
                                agent_last_content[window_name] = current_content
                                
                                # Extract agent type from window name
                                agent_type = window_name.replace('agent_', '').split('_', 1)[1] if 'agent_' in window_name else window_name
                                
                                # Send real-time agent thinking to WebSocket
                                if current_content:
                                    await notify_websocket_clients(session_id, {
                                        "type": "progress",
                                        "session_id": session_id,
                                        "progress_type": "agent_thinking",
                                        "agent": agent_type,
                                        "message": f"[{agent_type}] {current_content}",
                                        "content": current_content,
                                        "timestamp": datetime.now().isoformat()
                                    })
                
                # Send general progress update
                await notify_websocket_clients(session_id, {
                    "type": "progress",
                    "session_id": session_id,
                    "progress_type": "agent_progress", 
                    "message": f"{active_agents} agents working on analysis",
                    "active_agents": active_agents
                })
                
                print(f"[Monitor] Session {session_id}: {active_agents} agents active")
                
                # Check if analysis is complete (no more agent windows)
                if active_agents == 0:
                    session.status = "completed"
                    session.end_time = datetime.now()
                    session.results_available = True
                    session.message = "Analysis completed - all agents finished"
                    
                    await notify_websocket_clients(session_id, {
                        "type": "progress",
                        "session_id": session_id,
                        "progress_type": "analysis_completed",
                        "message": "🎉 Business analysis completed successfully!"
                    })
                    print(f"[Monitor] Session {session_id} completed")
                    break
                    
            else:
                # Tmux session doesn't exist - analysis might be done
                print(f"[Monitor] Tmux session {tmux_session} not found - analysis may be complete")
                await asyncio.sleep(5)
                
            # Wait before next check (shorter interval for real-time streaming)
            await asyncio.sleep(3)
            
    except Exception as e:
        print(f"Progress monitoring error for session {session_id}: {e}")

async def run_claude_sdk_analysis(session_id: str, request: AnalysisRequest):
    """Run business analysis using Claude SDK with real-time streaming"""
    try:
        session = active_sessions[session_id]
        session.status = "running"
        session.message = "Claude SDK agents are starting..."
        await notify_websocket_clients(session_id, session)
        
        print(f"[DEBUG] Starting Claude SDK analysis for session {session_id}")
        
        # Prepare excel files list - include file_path if provided
        excel_files = request.excel_files.copy() if request.excel_files else []
        if request.file_path and request.file_path not in excel_files:
            excel_files.append(request.file_path)
        
        # Enhanced business context with conversation history
        business_context = request.business_context or {
            "company": "Kop&Kande",
            "initiative": "Click & Collect Fee Implementation", 
            "proposed_fee": "25 DKK",
            "threshold": "150 DKK minimum order",
            "current_situation": "15.9% of C&C orders under 130 DKK",
            "annual_cost": "336,000 DKK",
            "average_order_size": "69 DKK ex moms",
            "market": "Nordic retail",
            "analysis_language": request.language
        }
        
        # Add conversation context and user message if provided
        if request.conversation_context:
            business_context["previous_conversation"] = request.conversation_context
        if request.message:
            business_context["user_request"] = request.message
        
        # Initialize the Claude SDK farm
        farm = ClaudeSDKAgentFarm(
            session_id=session_id,
            excel_files=excel_files,
            business_context=business_context,
            language=request.language,
            analysis_type=request.analysis_type,
            agents=request.agents
        )
        
        # Set up streaming callbacks
        async def handle_streaming_message(message: StreamingMessage):
            """Handle streaming messages from agents"""
            await notify_websocket_clients(session_id, {
                "type": "progress",
                "session_id": session_id,
                "progress_type": "agent_thinking",
                "agent": message.agent_type,
                "message": f"[{message.agent_type}] {message.content}",
                "content": message.content,
                "timestamp": message.timestamp.isoformat()
            })
            
            print(f"[STREAM] {message.agent_type}: {message.content[:100]}...")
        
        async def handle_progress_update(active_agents: int, status: str):
            """Handle progress updates"""
            session.agents_active = active_agents
            session.message = f"Claude SDK analysis: {status}"
            
            await notify_websocket_clients(session_id, {
                "type": "progress",
                "session_id": session_id,
                "progress_type": "agent_progress",
                "message": f"{active_agents} Claude SDK agents active",
                "active_agents": active_agents,
                "status": status
            })
            
            print(f"[PROGRESS] Session {session_id}: {active_agents} agents, status: {status}")
        
        farm.set_message_callback(handle_streaming_message)
        farm.set_progress_callback(handle_progress_update)
        
        # Update session status
        session.status = "running"
        session.agents_active = request.agents
        session.message = f"Running {request.agents} Claude SDK agents..."
        await notify_websocket_clients(session_id, session)
        
        # Run the analysis with streaming
        print(f"[DEBUG] Running Claude SDK farm with {request.agents} agents")
        results = await farm.run_analysis()
        
        # Analysis completed
        session.status = "completed"
        session.end_time = datetime.now()
        session.results_available = True
        session.message = "Claude SDK analysis completed successfully"
        await notify_websocket_clients(session_id, session)
        
        await notify_websocket_clients(session_id, {
            "type": "progress",
            "session_id": session_id,
            "progress_type": "analysis_completed",
            "message": "🎉 Claude SDK business analysis completed successfully!"
        })
        
        print(f"[DEBUG] Claude SDK analysis completed for session {session_id}")
        
    except Exception as e:
        # Handle errors
        print(f"[ERROR] Claude SDK analysis failed for session {session_id}: {str(e)}")
        session = active_sessions.get(session_id)
        if session:
            session.status = "error"
            session.end_time = datetime.now()
            session.message = f"Claude SDK analysis failed: {str(e)}"
            await notify_websocket_clients(session_id, session)

async def run_analysis_farm(session_id: str, request: AnalysisRequest):
    """Run the existing business analysis farm in background"""
    try:
        session = active_sessions[session_id]
        session.status = "running"
        session.message = "Business analysis agents are starting..."
        await notify_websocket_clients(session_id, session)
        
        # Use the existing BusinessAnalysisFarm class (completely unchanged)
        project_path = Path.cwd()
        
        # Prepare excel files list - include file_path if provided
        excel_files = request.excel_files.copy() if request.excel_files else []
        if request.file_path and request.file_path not in excel_files:
            excel_files.append(request.file_path)
        
        # Enhanced business context with conversation history
        business_context = request.business_context or {
            "company": "Kop&Kande",
            "initiative": "Click & Collect Fee Implementation", 
            "proposed_fee": "25 DKK",
            "threshold": "150 DKK minimum order",
            "current_situation": "15.9% of C&C orders under 130 DKK",
            "annual_cost": "336,000 DKK",
            "average_order_size": "69 DKK ex moms",
            "market": "Nordic retail",
            "analysis_language": request.language
        }
        
        # Add conversation context and user message if provided
        if request.conversation_context:
            business_context["previous_conversation"] = request.conversation_context
        if request.message:
            business_context["user_request"] = request.message
        
        # Initialize the farm with existing parameters
        farm = BusinessAnalysisFarm(
            path=str(project_path),
            agents=request.agents,
            session=f"business_agents_{session_id[:8]}",
            excel_files=excel_files,
            business_context=business_context,
            language=request.language,
            analysis_type=request.analysis_type,
            auto_restart=False,
            no_monitor=True,  # We'll monitor via WebSocket instead
            attach=False,
        )
        
        # Update session status
        session.status = "running"
        session.agents_active = request.agents
        session.message = f"Running {request.agents} business analysis agents..."
        await notify_websocket_clients(session_id, session)
        
        # Run the farm (this uses existing unchanged logic)
        farm.run()
        
        # Analysis completed
        session.status = "completed"
        session.end_time = datetime.now()
        session.results_available = True
        session.message = "Business analysis completed successfully"
        await notify_websocket_clients(session_id, session)
        
    except Exception as e:
        # Handle errors
        session = active_sessions.get(session_id)
        if session:
            session.status = "error"
            session.end_time = datetime.now()
            session.message = f"Analysis failed: {str(e)}"
            await notify_websocket_clients(session_id, session)

# ─────────────────────────────── Session Management ────────────────────────────── #

@app.get("/api/analysis/{session_id}/status")
async def get_session_status(session_id: str):
    """Get analysis session status"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return active_sessions[session_id]

@app.delete("/api/analysis/{session_id}")
async def stop_analysis(session_id: str):
    """Stop running analysis session"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Kill tmux session if it exists
        tmux_session = f"business_agents_{session_id[:8]}"
        subprocess.run(["tmux", "kill-session", "-t", tmux_session], 
                      capture_output=True, check=False)
        
        # Update session status
        session = active_sessions[session_id]
        session.status = "stopped"
        session.end_time = datetime.now()
        session.message = "Analysis stopped by user"
        
        await notify_websocket_clients(session_id, session)
        
        return {"message": "Analysis stopped successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop analysis: {str(e)}")

@app.get("/api/sessions")
async def get_sessions():
    """Get all analysis sessions"""
    return list(active_sessions.values())

# ─────────────────────────────── WebSocket Support ────────────────────────────── #

@app.websocket("/ws/analysis/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket for real-time analysis updates"""
    print(f"[DEBUG] WebSocket connection attempt for session {session_id}")
    await websocket.accept()
    websocket_connections[session_id] = websocket
    print(f"[DEBUG] WebSocket connected for session {session_id}")
    
    try:
        # Send initial status if session exists
        if session_id in active_sessions:
            session_data = active_sessions[session_id].dict()
            # Convert datetime objects to ISO strings for JSON serialization
            if session_data.get('start_time'):
                session_data['start_time'] = session_data['start_time'].isoformat()
            if session_data.get('end_time'):
                session_data['end_time'] = session_data['end_time'].isoformat()
            
            await websocket.send_json({
                "type": "status_update",
                "session_id": session_id,
                "data": session_data
            })
        
        # Keep connection alive
        while True:
            await websocket.receive_text()
    
    except WebSocketDisconnect:
        if session_id in websocket_connections:
            del websocket_connections[session_id]

async def notify_websocket_clients(session_id: str, message):
    """Notify WebSocket clients of status updates"""
    print(f"[DEBUG] Attempting to notify WebSocket clients for session {session_id}")
    if session_id in websocket_connections:
        try:
            websocket = websocket_connections[session_id]
            
            # Handle different message types
            if isinstance(message, dict):
                await websocket.send_json(message)
            else:
                # SessionStatus object - convert datetime fields to ISO strings
                session_data = message.dict()
                if session_data.get('start_time'):
                    session_data['start_time'] = session_data['start_time'].isoformat()
                if session_data.get('end_time'):
                    session_data['end_time'] = session_data['end_time'].isoformat()
                    
                await websocket.send_json({
                    "type": "status_update",
                    "session_id": session_id,
                    "data": session_data
                })
        except Exception as e:
            print(f"WebSocket error for session {session_id}: {e}")
            # Remove disconnected client
            if session_id in websocket_connections:
                del websocket_connections[session_id]

# ─────────────────────────────── Chat API ────────────────────────────── #

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """Handle chat requests from frontend with Claude API integration"""
    try:
        import httpx
        import pandas as pd
        
        # Get Claude API key from environment
        claude_api_key = os.getenv("CLAUDE_API_KEY")
        if not claude_api_key:
            raise HTTPException(status_code=500, detail="Claude API key not configured")
        
        # Process uploaded files and add their content to context
        file_context = ""
        if request.uploaded_file_paths:
            file_context = "\n\n=== UPLOADED FILES ANALYSIS ===\n"
            processed_files = set()  # Track processed files to avoid duplicates
            
            for file_path in request.uploaded_file_paths:
                try:
                    full_path = Path(file_path)
                    if full_path.exists() and full_path.suffix.lower() in ['.xlsx', '.xls', '.csv']:
                        # Extract original filename for deduplication
                        filename_parts = full_path.name.split('_', 1)
                        original_filename = filename_parts[1] if len(filename_parts) > 1 else full_path.name
                        
                        # Skip if we've already processed this original file
                        if original_filename in processed_files:
                            continue
                        processed_files.add(original_filename)
                        
                        file_context += f"\n--- FILE: {original_filename} ---\n"
                        
                        if full_path.suffix.lower() == '.csv':
                            df = pd.read_csv(full_path)
                        else:
                            # For Excel files, read all sheets
                            excel_data = pd.read_excel(full_path, sheet_name=None)
                            for sheet_name, df in excel_data.items():
                                file_context += f"\nSheet: {sheet_name}\n"
                                file_context += f"Shape: {df.shape[0]} rows × {df.shape[1]} columns\n"
                                file_context += f"Columns: {list(df.columns)}\n"
                                
                                # Add sample data (first 5 rows)
                                file_context += "\nSample Data:\n"
                                file_context += df.head().to_string(max_cols=10)
                                
                                # Add basic statistics for numeric columns
                                numeric_cols = df.select_dtypes(include=['number']).columns
                                if len(numeric_cols) > 0:
                                    file_context += f"\n\nNumeric Summary:\n"
                                    file_context += df[numeric_cols].describe().to_string()
                                
                                file_context += "\n" + "="*50 + "\n"
                                
                except Exception as e:
                    file_context += f"\nError reading {file_path}: {str(e)}\n"
        
        # Format messages for Claude API
        messages = []
        for msg in request.messages:
            content = msg.content
            # Add file context to the first user message if files are present
            if msg.role == "user" and file_context and len(messages) == 0:
                content = msg.content + file_context
                
            messages.append({
                "role": msg.role,
                "content": content
            })
        
        # Add business analysis context to system message
        system_message = """You are a business analysis assistant integrated with a powerful multi-agent business analysis farm. 

You have access to:
- Excel data processing and analysis capabilities
- Multiple specialized business analysis agents (financial, customer, pricing, market, operations, risk, strategic, etc.)
- Real-time analysis orchestration
- Comprehensive business intelligence generation

When users upload Excel files, you can see their content and provide:
- Data structure analysis and insights
- Business metrics identification
- Trend analysis and patterns
- Strategic recommendations based on the data
- Guidance on what types of deeper analysis would be valuable

When users ask about business analysis, help them understand:
- How to interpret their uploaded data
- What types of business analysis are available  
- Strategic insights and recommendations
- Next steps for comprehensive multi-agent analysis

Be helpful, professional, and focus on business analysis and strategic decision-making. Reference specific data points from uploaded files when providing insights."""
        
        # Prepare Claude API request
        claude_request = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 1024,
            "system": system_message,
            "messages": messages
        }
        
        # Call Claude API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": claude_api_key,
                    "anthropic-version": "2023-06-01"
                },
                json=claude_request,
                timeout=30.0
            )
            
            if response.status_code != 200:
                error_detail = f"Claude API error: {response.status_code} {response.text}"
                raise HTTPException(status_code=500, detail=error_detail)
            
            result = response.json()
            
            # Extract content from Claude response
            content = result.get("content", [])
            if content and len(content) > 0:
                response_text = content[0].get("text", "No response generated")
            else:
                response_text = "No response generated"
        
        return {
            "content": response_text,
            "role": "assistant"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat request failed: {str(e)}")

# ─────────────────────────────── Health Check ────────────────────────────── #

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(active_sessions)
    }

# ─────────────────────────────── Main Entry Point ────────────────────────────── #

if __name__ == "__main__":
    print("🏢 Starting Business Analysis Agent Farm Backend Server...")
    print("📊 Frontend integration: http://localhost:3000")
    print("🔧 API documentation: http://localhost:8000/docs")
    print("💡 WebSocket endpoint: ws://localhost:8000/ws/analysis/{session_id}")
    
    uvicorn.run(
        "backend_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )