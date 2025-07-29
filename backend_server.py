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
import pandas as pd
import numpy as np
from decimal import Decimal

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

# ─────────────────────────────── Excel Processing Engine ────────────────────────────── #

class ExcelParsingEngine:
    """Enhanced Excel parsing with business intelligence extraction"""
    
    def __init__(self):
        self.danish_financial_terms = [
            'pris', 'beløb', 'omkost', 'gebyr', 'omsæt', 'indtægt', 'udgifte', 'profit', 
            'margin', 'dkk', 'kr', 'kroner', 'moms', 'ex moms', 'inkl moms', 'total', 
            'sum', 'gns', 'gennemsnit', 'andel', 'procent', 'rabat', 'underskud', 'db'
        ]
        
        self.english_financial_terms = [
            'price', 'amount', 'cost', 'fee', 'revenue', 'income', 'expense', 'profit',
            'margin', 'total', 'sum', 'average', 'avg', 'percentage', 'percent', 'discount',
            'loss', 'contribution', 'gross', 'net'
        ]
        
        self.customer_terms = [
            'kunde', 'customer', 'order', 'ordre', 'segment', 'bruger', 'user', 
            'køb', 'purchase', 'antal', 'count', 'frequency', 'hyppighed'
        ]
        
        self.operational_terms = [
            'process', 'proces', 'tid', 'time', 'kapacitet', 'capacity', 'effektivitet',
            'efficiency', 'volumen', 'volume', 'lager', 'stock', 'inventory'
        ]
        
    def parse_excel_file(self, file_path: str) -> Dict[str, Any]:
        """Parse Excel file and extract comprehensive business data"""
        try:
            # Read all sheets
            excel_data = pd.read_excel(file_path, sheet_name=None, engine='openpyxl')
            
            # Process each sheet
            parsed_sheets = {}
            business_insights = []
            key_metrics = {}
            
            for sheet_name, df in excel_data.items():
                sheet_analysis = self._analyze_sheet(df, sheet_name)
                parsed_sheets[sheet_name] = sheet_analysis
                
                # Collect business insights
                business_insights.extend(sheet_analysis.get('insights', []))
                
                # Collect key metrics
                if sheet_analysis.get('key_metrics'):
                    key_metrics[sheet_name] = sheet_analysis['key_metrics']
            
            # Create comprehensive result
            result = {
                "file_info": {
                    "name": Path(file_path).name,
                    "size": Path(file_path).stat().st_size,
                    "sheet_count": len(parsed_sheets),
                    "sheet_names": list(parsed_sheets.keys())
                },
                "parsed_data": parsed_sheets,
                "business_summary": {
                    "key_metrics": key_metrics,
                    "insights": business_insights,
                    "data_quality": self._assess_data_quality(parsed_sheets),
                    "business_context": self._extract_business_context(parsed_sheets)
                }
            }
            
            return result
            
        except Exception as e:
            raise Exception(f"Excel parsing failed: {str(e)}")
    
    def _analyze_sheet(self, df: pd.DataFrame, sheet_name: str) -> Dict[str, Any]:
        """Analyze individual Excel sheet"""
        # Clean the DataFrame
        df_cleaned = df.dropna(how='all').dropna(axis=1, how='all')
        
        if df_cleaned.empty:
            return {
                "sheet_name": sheet_name,
                "empty": True,
                "message": "Sheet is empty or contains no usable data"
            }
        
        # Convert DataFrame to JSON-serializable format
        data_records = []
        for idx, row in df_cleaned.iterrows():
            record = {}
            for col in df_cleaned.columns:
                value = row[col]
                # Handle different data types
                if pd.isna(value):
                    record[str(col)] = None
                elif isinstance(value, (np.integer, int)):
                    record[str(col)] = int(value)
                elif isinstance(value, (np.floating, float)):
                    record[str(col)] = float(value) if not np.isnan(value) else None
                elif isinstance(value, pd.Timestamp):
                    record[str(col)] = value.isoformat()
                else:
                    record[str(col)] = str(value)
            data_records.append(record)
        
        # Analyze columns
        column_analysis = {}
        for col in df_cleaned.columns:
            col_data = df_cleaned[col].dropna()
            column_analysis[str(col)] = self._analyze_column(col_data, str(col))
        
        # Extract business insights
        insights = self._extract_sheet_insights(df_cleaned, sheet_name)
        
        # Calculate key metrics
        key_metrics = self._calculate_key_metrics(df_cleaned)
        
        return {
            "sheet_name": sheet_name,
            "dimensions": {
                "rows": len(df_cleaned),
                "columns": len(df_cleaned.columns)
            },
            "columns": [str(col) for col in df_cleaned.columns],
            "data": data_records,
            "column_analysis": column_analysis,
            "key_metrics": key_metrics,
            "insights": insights,
            "data_types": self._get_data_types(df_cleaned)
        }
    
    def _analyze_column(self, col_data: pd.Series, col_name: str) -> Dict[str, Any]:
        """Analyze individual column"""
        analysis = {
            "name": col_name,
            "count": len(col_data),
            "non_null_count": col_data.count(),
            "data_type": str(col_data.dtype),
            "business_category": self._categorize_business_column(col_name)
        }
        
        # Numeric analysis
        if pd.api.types.is_numeric_dtype(col_data):
            analysis.update({
                "statistics": {
                    "mean": float(col_data.mean()),
                    "median": float(col_data.median()),
                    "std": float(col_data.std()) if len(col_data) > 1 else 0,
                    "min": float(col_data.min()),
                    "max": float(col_data.max()),
                    "sum": float(col_data.sum())
                },
                "is_financial": self._is_financial_column(col_name, col_data),
                "is_percentage": self._is_percentage_column(col_data),
                "currency_detected": self._detect_currency(col_name, col_data)
            })
        
        # Categorical analysis
        elif pd.api.types.is_object_dtype(col_data):
            unique_values = col_data.unique()
            analysis.update({
                "unique_count": len(unique_values),
                "unique_values": [str(v) for v in unique_values[:10]],  # First 10 values
                "is_categorical": len(unique_values) <= 20,
                "most_common": str(col_data.mode().iloc[0]) if len(col_data.mode()) > 0 else None
            })
        
        return analysis
    
    def _categorize_business_column(self, col_name: str) -> str:
        """Categorize column based on business context"""
        col_lower = col_name.lower()
        
        # Check financial terms
        if any(term in col_lower for term in self.danish_financial_terms + self.english_financial_terms):
            return "financial"
        
        # Check customer terms
        if any(term in col_lower for term in self.customer_terms):
            return "customer"
        
        # Check operational terms
        if any(term in col_lower for term in self.operational_terms):
            return "operational"
        
        return "general"
    
    def _is_financial_column(self, col_name: str, col_data: pd.Series) -> bool:
        """Determine if column contains financial data"""
        col_lower = col_name.lower()
        
        # Check name patterns
        if any(term in col_lower for term in self.danish_financial_terms + self.english_financial_terms):
            return True
        
        # Check value patterns (large numbers often indicate financial data)
        if pd.api.types.is_numeric_dtype(col_data):
            max_val = col_data.max()
            if max_val > 1000:  # Likely financial if max > 1000
                return True
        
        return False
    
    def _is_percentage_column(self, col_data: pd.Series) -> bool:
        """Determine if column contains percentage data"""
        if not pd.api.types.is_numeric_dtype(col_data):
            return False
        
        max_val = col_data.max()
        min_val = col_data.min()
        
        # Check if values are in 0-1 range (decimal percentages)
        if max_val <= 1.0 and min_val >= 0:
            return True
        
        # Check if values are in 0-100 range
        if max_val <= 100 and min_val >= 0 and col_data.mean() < 50:
            return True
        
        return False
    
    def _detect_currency(self, col_name: str, col_data: pd.Series) -> str:
        """Detect currency type"""
        col_lower = col_name.lower()
        
        if 'dkk' in col_lower or 'kr' in col_lower or 'kroner' in col_lower:
            return "DKK"
        elif 'eur' in col_lower or 'euro' in col_lower:
            return "EUR"
        elif 'usd' in col_lower or 'dollar' in col_lower:
            return "USD"
        
        return "unknown"
    
    def _extract_sheet_insights(self, df: pd.DataFrame, sheet_name: str) -> List[str]:
        """Extract business insights from sheet"""
        insights = []
        
        # Financial insights
        financial_cols = [col for col in df.columns if self._is_financial_column(str(col), df[col])]
        if financial_cols:
            insights.append(f"Sheet '{sheet_name}' contains {len(financial_cols)} financial metrics: {', '.join(map(str, financial_cols[:3]))}")
        
        # Data size insights
        if len(df) > 1000:
            insights.append(f"Large dataset with {len(df)} records - suitable for statistical analysis")
        elif len(df) < 10:
            insights.append(f"Small dataset with {len(df)} records - may require careful interpretation")
        
        # Missing data insights
        missing_data_cols = [col for col in df.columns if df[col].isna().sum() > len(df) * 0.5]
        if missing_data_cols:
            insights.append(f"High missing data in columns: {', '.join(map(str, missing_data_cols[:3]))}")
        
        return insights
    
    def _calculate_key_metrics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate key business metrics from the data"""
        metrics = {}
        
        # Find potential revenue/cost columns
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            col_name = str(col).lower()
            if any(term in col_name for term in ['total', 'sum', 'omsæt', 'revenue', 'cost', 'omkost']):
                col_data = df[col].dropna()
                if len(col_data) > 0:
                    metrics[str(col)] = {
                        "total": float(col_data.sum()),
                        "average": float(col_data.mean()),
                        "count": len(col_data)
                    }
        
        return metrics
    
    def _get_data_types(self, df: pd.DataFrame) -> Dict[str, str]:
        """Get data types for all columns"""
        return {str(col): str(dtype) for col, dtype in df.dtypes.items()}
    
    def _assess_data_quality(self, parsed_sheets: Dict[str, Any]) -> Dict[str, Any]:
        """Assess overall data quality"""
        total_records = sum(sheet.get('dimensions', {}).get('rows', 0) for sheet in parsed_sheets.values())
        
        quality_score = 0
        issues = []
        
        for sheet_name, sheet_data in parsed_sheets.items():
            if sheet_data.get('empty'):
                issues.append(f"Sheet '{sheet_name}' is empty")
                continue
            
            # Check for missing data
            dimensions = sheet_data.get('dimensions', {})
            if dimensions.get('rows', 0) > 0:
                quality_score += 20
            
            # Check for financial data
            if any(col.get('is_financial', False) for col in sheet_data.get('column_analysis', {}).values()):
                quality_score += 30
        
        return {
            "quality_score": min(quality_score, 100),
            "total_records": total_records,
            "issues": issues,
            "assessment": "Good" if quality_score > 70 else "Fair" if quality_score > 40 else "Poor"
        }
    
    def _extract_business_context(self, parsed_sheets: Dict[str, Any]) -> Dict[str, Any]:
        """Extract business context from the data"""
        context = {
            "industry_indicators": [],
            "analysis_types": [],
            "key_business_areas": []
        }
        
        # Analyze all column names to infer business context
        all_columns = []
        for sheet_data in parsed_sheets.values():
            if not sheet_data.get('empty'):
                all_columns.extend(sheet_data.get('columns', []))
        
        column_text = ' '.join(all_columns).lower()
        
        # Detect business areas
        if any(term in column_text for term in ['click', 'collect', 'c&c', 'butik', 'shop']):
            context['key_business_areas'].append('retail_operations')
        
        if any(term in column_text for term in ['kunde', 'customer', 'ordre', 'order']):
            context['key_business_areas'].append('customer_analysis')
        
        if any(term in column_text for term in self.danish_financial_terms[:10]):
            context['analysis_types'].append('financial_analysis')
        
        return context

# ─────────────────────────────── File Upload Handler ────────────────────────────── #

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Handle Excel file uploads with immediate parsing and business intelligence extraction"""
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
        
        # Parse Excel file immediately using the enhanced parsing engine
        parser = ExcelParsingEngine()
        parsed_data = parser.parse_excel_file(str(file_path))
        
        # Save parsed data as JSON for quick access
        json_filename = f"{file_id}_{file.filename}.json"
        json_path = UPLOADS_DIR / json_filename
        
        with open(json_path, 'w', encoding='utf-8') as json_file:
            json.dump(parsed_data, json_file, indent=2, ensure_ascii=False)
        
        # Return comprehensive response with parsed data
        response = {
            "file_id": file_id,
            "filename": file.filename,
            "file_path": str(file_path),
            "json_path": str(json_path),
            "size": file_path.stat().st_size,
            "uploaded_at": datetime.now().isoformat(),
            "parsed_data": parsed_data,
            "parsing_status": "success",
            "business_insights": parsed_data.get("business_summary", {}).get("insights", []),
            "data_quality": parsed_data.get("business_summary", {}).get("data_quality", {}),
            "sheets_processed": len(parsed_data.get("parsed_data", {}))
        }
        
        return response
    
    except Exception as e:
        # Return error information but still save the file
        error_response = {
            "file_id": file_id if 'file_id' in locals() else str(uuid.uuid4()),
            "filename": file.filename,
            "file_path": str(file_path) if 'file_path' in locals() else None,
            "size": file_path.stat().st_size if 'file_path' in locals() and file_path.exists() else 0,
            "uploaded_at": datetime.now().isoformat(),
            "parsing_status": "error",
            "error": str(e),
            "parsed_data": None
        }
        
        # Don't raise HTTPException, return error info so file is still accessible
        return error_response

@app.get("/api/files")
async def list_uploaded_files():
    """List all uploaded files with parsing status and business insights"""
    try:
        files = []
        seen_files = {}  # Track by original filename to avoid duplicates
        
        if UPLOADS_DIR.exists():
            for file_path in UPLOADS_DIR.glob("*"):
                if file_path.is_file() and file_path.suffix.lower() in ['.xlsx', '.xls', '.csv']:
                    # Extract original filename (everything after first underscore)
                    filename_parts = file_path.name.split('_', 1)
                    original_filename = filename_parts[1] if len(filename_parts) > 1 else file_path.name
                    
                    # Check for corresponding JSON file
                    json_path = file_path.with_suffix(file_path.suffix + '.json')
                    parsed_data_available = json_path.exists()
                    parsing_summary = None
                    
                    if parsed_data_available:
                        try:
                            with open(json_path, 'r', encoding='utf-8') as f:
                                parsed_data = json.load(f)
                                parsing_summary = {
                                    "sheets_count": len(parsed_data.get("parsed_data", {})),
                                    "total_records": sum(
                                        sheet.get("dimensions", {}).get("rows", 0) 
                                        for sheet in parsed_data.get("parsed_data", {}).values()
                                        if not sheet.get("empty", True)
                                    ),
                                    "data_quality": parsed_data.get("business_summary", {}).get("data_quality", {}).get("assessment", "Unknown"),
                                    "business_areas": parsed_data.get("business_summary", {}).get("business_context", {}).get("key_business_areas", []),
                                    "key_insights_count": len(parsed_data.get("business_summary", {}).get("insights", []))
                                }
                        except Exception:
                            parsing_summary = {"error": "Failed to load parsed data"}
                    
                    file_info = {
                        "filename": original_filename,
                        "path": str(file_path),
                        "json_path": str(json_path) if parsed_data_available else None,
                        "size": file_path.stat().st_size,
                        "uploaded_at": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                        "parsed_data_available": parsed_data_available,
                        "parsing_summary": parsing_summary
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

@app.get("/api/files/{file_id}/parsed-data")
async def get_parsed_data(file_id: str):
    """Get parsed JSON data for a specific file"""
    try:
        # Find the JSON file for this file_id
        json_files = list(UPLOADS_DIR.glob(f"{file_id}_*.json"))
        
        if not json_files:
            raise HTTPException(status_code=404, detail="Parsed data not found for this file")
        
        json_path = json_files[0]  # Take the first match
        
        with open(json_path, 'r', encoding='utf-8') as f:
            parsed_data = json.load(f)
        
        return {
            "file_id": file_id,
            "json_path": str(json_path),
            "parsed_data": parsed_data,
            "last_updated": datetime.fromtimestamp(json_path.stat().st_mtime).isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve parsed data: {str(e)}")

@app.post("/api/files/reparse")
async def reparse_file(file_path: str):
    """Reparse an existing Excel file with updated parsing logic"""
    try:
        file_path_obj = Path(file_path)
        
        if not file_path_obj.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        # Parse the file again
        parser = ExcelParsingEngine()
        parsed_data = parser.parse_excel_file(str(file_path_obj))
        
        # Save updated parsed data
        json_path = file_path_obj.with_suffix(file_path_obj.suffix + '.json')
        
        with open(json_path, 'w', encoding='utf-8') as json_file:
            json.dump(parsed_data, json_file, indent=2, ensure_ascii=False)
        
        return {
            "message": "File reparsed successfully",
            "file_path": str(file_path_obj),
            "json_path": str(json_path),
            "parsed_data": parsed_data,
            "reparsed_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reparse file: {str(e)}")

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
        
        # Load parsed data for all Excel files
        combined_parsed_data = {}
        for file_path in excel_files:
            json_path = Path(file_path).with_suffix(Path(file_path).suffix + '.json')
            if json_path.exists():
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        file_parsed_data = json.load(f)
                        # Merge parsed data from multiple files
                        if not combined_parsed_data:
                            combined_parsed_data = file_parsed_data
                        else:
                            # Merge multiple files' data
                            combined_parsed_data['parsed_data'].update(file_parsed_data.get('parsed_data', {}))
                            combined_parsed_data['business_summary']['insights'].extend(
                                file_parsed_data.get('business_summary', {}).get('insights', [])
                            )
                except Exception as e:
                    print(f"Warning: Could not load parsed data for {file_path}: {e}")
        
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
        
        # Initialize the Claude SDK farm with parsed data
        farm = ClaudeSDKAgentFarm(
            session_id=session_id,
            excel_files=excel_files,
            parsed_data=combined_parsed_data,  # Pass the parsed JSON data
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