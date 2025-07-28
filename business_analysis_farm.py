#!/usr/bin/env python3
"""
Business Analysis Agent Farm - Multi-Agent Business Intelligence Orchestrator
Adapts the Claude Code Agent Farm for comprehensive business case analysis and strategic planning
"""

import contextlib
import fcntl
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import pandas as pd
from datetime import datetime
from pathlib import Path
from random import randint
from typing import Any, Dict, List, Optional, Tuple, Union

import typer
from rich import box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)
from rich.prompt import Confirm
from rich.table import Table

app = typer.Typer(
    rich_markup_mode="rich",
    help="Orchestrate multiple Claude business analysis agents for parallel business intelligence using tmux",
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console(stderr=True)  # Use stderr for progress/info so stdout remains clean

# ─────────────────────────────── Configuration ────────────────────────────── #

def interruptible_confirm(message: str, default: bool = False) -> bool:
    """Confirmation prompt that returns default on KeyboardInterrupt"""
    try:
        return Confirm.ask(message, default=default)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted - using default response[/yellow]")
        return default

# ─────────────────────────────── Constants ────────────────────────────────── #

MONITOR_STATE_FILE = ".business_analysis_farm_state.json"

# Business Analysis Agent Specializations
BUSINESS_AGENT_TYPES = {
    "financial_modeling": {
        "description": "Unit economics, ROI modeling, cash flow analysis, and financial projections",
        "prompt_focus": "financial analysis, ROI calculations, unit economics modeling",
        "excel_sheets": ["financials", "calculations", "costs", "revenue"]
    },
    "customer_analytics": {
        "description": "Customer segmentation, behavior analysis, CLV modeling, and retention analysis", 
        "prompt_focus": "customer analysis, segmentation, lifetime value, behavioral patterns",
        "excel_sheets": ["customers", "segments", "behavior", "retention"]
    },
    "pricing_strategy": {
        "description": "Pricing optimization, elasticity modeling, competitive pricing, and value-based pricing",
        "prompt_focus": "pricing strategy, elasticity analysis, competitive pricing, value propositions",
        "excel_sheets": ["pricing", "competitors", "elasticity", "margins"]
    },
    "market_intelligence": {
        "description": "Competitive analysis, market sizing, trend analysis, and industry research",
        "prompt_focus": "market research, competitive intelligence, industry trends, market sizing",
        "excel_sheets": ["market", "competitors", "trends", "sizing"]
    },
    "operations_analytics": {
        "description": "Process optimization, efficiency analysis, capacity planning, and operational metrics",
        "prompt_focus": "operations optimization, process analysis, efficiency metrics, capacity planning",
        "excel_sheets": ["operations", "processes", "capacity", "efficiency"]
    },
    "risk_assessment": {
        "description": "Risk identification, scenario modeling, sensitivity analysis, and mitigation strategies",
        "prompt_focus": "risk analysis, scenario planning, sensitivity modeling, mitigation strategies",
        "excel_sheets": ["risks", "scenarios", "sensitivity", "mitigation"]
    },
    "strategic_planning": {
        "description": "Strategic framework analysis, growth planning, competitive positioning, and market entry",
        "prompt_focus": "strategic planning, growth strategies, competitive positioning, market opportunities",
        "excel_sheets": ["strategy", "growth", "positioning", "opportunities"]
    },
    "data_integration": {
        "description": "Data harmonization, quality assessment, integration analysis, and insights synthesis",
        "prompt_focus": "data analysis, integration, quality assessment, insights synthesis",
        "excel_sheets": ["data", "quality", "integration", "sources"]
    },
    "qa_validation": {
        "description": "Analysis validation, consistency checking, methodology review, and quality assurance",
        "prompt_focus": "quality assurance, validation, consistency checking, methodology review",
        "excel_sheets": ["validation", "quality", "consistency", "methodology"]
    },
    "synthesis_coordination": {
        "description": "Multi-agent coordination, insight synthesis, executive reporting, and strategic communication",
        "prompt_focus": "synthesis coordination, executive reporting, strategic insights, communication",
        "excel_sheets": ["synthesis", "executive", "insights", "recommendations"]
    },
    "executive_report_generator": {
        "description": "Board-ready presentation creation, visual storytelling, executive communication, and success metrics",
        "prompt_focus": "executive presentations, visual storytelling, board communication, success metrics",
        "excel_sheets": ["executive", "presentations", "metrics", "storytelling"]
    },
    "implementation_planning": {
        "description": "Change management, rollout planning, risk mitigation, and stakeholder communication strategies",
        "prompt_focus": "implementation planning, change management, rollout strategies, stakeholder engagement",
        "excel_sheets": ["implementation", "rollout", "change", "stakeholders"]
    },
    "financial_audit_compliance": {
        "description": "Financial calculation auditing, regulatory compliance checking, and audit trail documentation",
        "prompt_focus": "financial auditing, compliance checking, audit trails, regulatory requirements",
        "excel_sheets": ["audit", "compliance", "financial", "regulatory"]
    },
    "business_case_writer": {
        "description": "Comprehensive business case documentation, executive summary writing, and decision framework creation",
        "prompt_focus": "business case writing, executive summaries, decision frameworks, strategic documentation",
        "excel_sheets": ["business_case", "executive", "decisions", "documentation"]
    },
    "implementation_coordinator": {
        "description": "Project coordination, timeline management, resource allocation, and success tracking for implementation",
        "prompt_focus": "project coordination, timeline management, resource allocation, implementation tracking",
        "excel_sheets": ["coordination", "timelines", "resources", "tracking"]
    }
}

# ─────────────────────────────── Helper Functions ─────────────────────────── #

def run(cmd: str, *, check: bool = True, quiet: bool = False, capture: bool = False) -> Tuple[int, str, str]:
    """Execute shell command with optional output capture
    
    When capture=False, output is streamed to terminal unless quiet=True
    When capture=True, output is captured and returned
    """
    if not quiet:
        console.log(cmd, style="cyan")

    # Parse command for shell safety when possible
    cmd_arg: Union[str, List[str]]
    try:
        # Try to parse as a list of arguments for safer execution
        cmd_list = shlex.split(cmd)
        use_shell = False
        cmd_arg = cmd_list
    except ValueError:
        # Fall back to shell=True for complex commands with pipes, redirects, etc.
        cmd_list = []  # Not used when shell=True
        use_shell = True
        cmd_arg = cmd

    if capture:
        result = subprocess.run(cmd_arg, shell=use_shell, capture_output=True, text=True, check=check)
        return result.returncode, result.stdout or "", result.stderr or ""
    else:
        # Stream output to terminal when not capturing
        # Preserve stderr even in quiet-mode so that exceptions contain detail
        if quiet:
            result = subprocess.run(cmd_arg, shell=use_shell, capture_output=True, text=True, check=check)
            return result.returncode, result.stdout or "", result.stderr or ""
        stdout_pipe = None
        stderr_pipe = subprocess.STDOUT
        try:
            result = subprocess.run(
                cmd_arg, shell=use_shell, stdout=stdout_pipe, stderr=stderr_pipe, text=True, check=check
            )
            return result.returncode, "", ""
        except subprocess.CalledProcessError as e:
            return e.returncode, "", str(e)


def find_tmux() -> str:
    """Find tmux executable"""
    tmux_path = subprocess.run(["which", "tmux"], capture_output=True, text=True).stdout.strip()
    if not tmux_path:
        console.print("[red]✖ tmux not found in PATH[/red]")
        console.print("Please install tmux: brew install tmux (macOS) or apt install tmux (Ubuntu)")
        sys.exit(1)
    return tmux_path


def tmux_send(target: str, data: str, enter: bool = True, update_heartbeat: bool = True) -> None:
    """Send keystrokes to a tmux pane (binary-safe)"""
    max_retries = 3
    base_delay = 0.5

    for attempt in range(max_retries):
        try:
            if data:
                # Use tmux buffer API for robustness with large payloads
                # Create a temporary file with the data to avoid shell-quoting issues
                import uuid

                with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
                    tmp.write(data)
                    tmp_path = tmp.name

                buf_name = f"businessfarm_{uuid.uuid4().hex[:8]}"

                try:
                    # Load the data into a tmux buffer
                    run(f"tmux load-buffer -b {buf_name} {shlex.quote(tmp_path)}", quiet=True)
                    # Paste the buffer into the target pane and delete the buffer (-d)
                    run(f"tmux paste-buffer -d -b {buf_name} -t {target}", quiet=True)
                finally:
                    # Clean up temp file
                    with contextlib.suppress(FileNotFoundError):
                        os.unlink(tmp_path)

                # CRITICAL: Small delay between pasting and Enter for Claude Code
                if enter:
                    time.sleep(0.2)

            if enter:
                run(f"tmux send-keys -t {target} C-m", quiet=True)
            
            # Update heartbeat if requested (default True) - simplified for business farm
            break
        except subprocess.CalledProcessError:
            if attempt < max_retries - 1:
                # Exponential backoff: 0.5s, 1s, 2s
                time.sleep(base_delay * (2**attempt))
            else:
                raise


def tmux_capture(target: str) -> str:
    """Capture content from a tmux pane"""
    max_retries = 3

    for attempt in range(max_retries):
        try:
            _, stdout, _ = run(f"tmux capture-pane -t {target} -p", quiet=True, capture=True)
            return stdout
        except subprocess.CalledProcessError:
            if attempt < max_retries - 1:
                time.sleep(0.2)
            else:
                # Return empty string on persistent failure
                return ""
    return ""


def ensure_session_exists(session: str, tmux_mouse: bool = True) -> None:
    """Create tmux session if it doesn't exist"""
    # Check if session exists
    result = subprocess.run(
        ["tmux", "has-session", "-t", session], capture_output=True, text=True
    )
    
    if result.returncode != 0:
        # Session doesn't exist, create it
        console.print(f"[blue]Creating tmux session '{session}'[/blue]")
        subprocess.run(["tmux", "new-session", "-d", "-s", session], check=True)
        
        # Configure mouse support
        if tmux_mouse:
            subprocess.run(["tmux", "set-option", "-t", session, "mouse", "on"], check=True)


# ─────────────────────────────── Excel Processing ─────────────────────────── #

class ExcelProcessor:
    """Handles Excel file processing and business data extraction"""
    
    def __init__(self, excel_files: List[str], business_context: Dict[str, Any]):
        self.excel_files = excel_files
        self.business_context = business_context
        self.processed_data = {}
        
    def process_excel_files(self) -> Dict[str, Any]:
        """Process Excel files and extract business analysis tasks"""
        console.print("[blue]Processing Excel files for business analysis...[/blue]")
        
        all_data = {}
        business_tasks = []
        
        for excel_file in self.excel_files:
            if not Path(excel_file).exists():
                console.print(f"[yellow]Warning: Excel file {excel_file} not found[/yellow]")
                continue
                
            try:
                # Read Excel file with multiple sheets
                excel_data = pd.read_excel(excel_file, sheet_name=None)
                all_data[excel_file] = excel_data
                
                # Extract business metrics from each sheet
                for sheet_name, df in excel_data.items():
                    metrics = self._extract_business_metrics(df, sheet_name, excel_file)
                    if metrics:
                        business_tasks.extend(self._create_analysis_tasks(metrics, sheet_name))
                        
            except Exception as e:
                console.print(f"[red]Error processing {excel_file}: {e}[/red]")
                continue
        
        # Create comprehensive business analysis tasks
        comprehensive_tasks = self._create_comprehensive_tasks(all_data)
        business_tasks.extend(comprehensive_tasks)
        
        self.processed_data = {
            "excel_data": all_data,
            "business_tasks": business_tasks,
            "business_context": self.business_context,
            "task_count": len(business_tasks)
        }
        
        return self.processed_data
    
    def _extract_business_metrics(self, df: pd.DataFrame, sheet_name: str, file_name: str) -> Dict[str, Any]:
        """Extract key business metrics and full data content from DataFrame"""
        
        # Clean the DataFrame - remove completely empty rows/columns
        df_cleaned = df.dropna(how='all').dropna(axis=1, how='all')
        
        # Convert DataFrame to structured text representation
        data_as_text = self._dataframe_to_structured_text(df_cleaned, sheet_name)
        
        # Extract statistical summary
        numeric_summary = self._get_numeric_summary(df_cleaned)
        
        metrics = {
            "sheet_name": sheet_name,
            "file_name": file_name,
            "row_count": len(df_cleaned),
            "column_count": len(df_cleaned.columns),
            "columns": list(df_cleaned.columns),
            "data_content": data_as_text,  # Full structured data for agents
            "numeric_summary": numeric_summary,
            "data_summary": {}
        }
        
        # Look for financial metrics
        financial_columns = [col for col in df_cleaned.columns if any(term in str(col).lower() for term in 
                           ['cost', 'revenue', 'profit', 'price', 'amount', 'value', 'dkk', 'kr', 'beløb', 'pris'])]
        
        # Look for customer metrics  
        customer_columns = [col for col in df_cleaned.columns if any(term in str(col).lower() for term in
                          ['customer', 'user', 'segment', 'order', 'frequency', 'retention', 'kunde', 'ordre'])]
        
        # Look for operational metrics
        operational_columns = [col for col in df_cleaned.columns if any(term in str(col).lower() for term in
                             ['volume', 'capacity', 'efficiency', 'time', 'process', 'operation', 'proces', 'tid'])]
        
        # Identify key data patterns
        key_insights = self._identify_key_data_patterns(df_cleaned)
        
        metrics["data_summary"] = {
            "financial_metrics": financial_columns,
            "customer_metrics": customer_columns, 
            "operational_metrics": operational_columns,
            "numeric_columns": list(df_cleaned.select_dtypes(include=['number']).columns),
            "date_columns": list(df_cleaned.select_dtypes(include=['datetime']).columns),
            "key_insights": key_insights
        }
        
        return metrics
    
    def _dataframe_to_structured_text(self, df: pd.DataFrame, sheet_name: str) -> str:
        """Convert DataFrame to structured text format for agent analysis"""
        
        text_output = []
        text_output.append(f"=== EXCEL SHEET: {sheet_name} ===")
        text_output.append(f"Dimensions: {len(df)} rows × {len(df.columns)} columns")
        text_output.append("")
        
        # Add column information
        text_output.append("COLUMNS:")
        for i, col in enumerate(df.columns, 1):
            col_type = str(df[col].dtype)
            non_null_count = df[col].count()
            text_output.append(f"  {i}. {col} ({col_type}) - {non_null_count} non-null values")
        text_output.append("")
        
        # Add sample data (first 10 rows)
        text_output.append("DATA SAMPLE (First 10 rows):")
        sample_df = df.head(10)
        
        # Format the data table
        try:
            text_output.append(sample_df.to_string(index=True, max_cols=None))
        except Exception:
            text_output.append(str(sample_df))
        text_output.append("")
        
        # Add data summary statistics for numeric columns
        numeric_cols = df.select_dtypes(include=['number']).columns
        if len(numeric_cols) > 0:
            text_output.append("NUMERIC SUMMARY STATISTICS:")
            summary_stats = df[numeric_cols].describe()
            try:
                text_output.append(summary_stats.to_string())
            except Exception:
                text_output.append(str(summary_stats))
            text_output.append("")
        
        # Add unique value counts for categorical columns
        categorical_cols = df.select_dtypes(include=['object']).columns
        if len(categorical_cols) > 0:
            text_output.append("CATEGORICAL DATA ANALYSIS:")
            for col in categorical_cols[:5]:  # Limit to first 5 categorical columns
                unique_count = df[col].nunique()
                if unique_count <= 20:  # Only show value counts for columns with reasonable unique values
                    text_output.append(f"  {col} - Unique values ({unique_count}):")
                    value_counts = df[col].value_counts().head(10)
                    for value, count in value_counts.items():
                        text_output.append(f"    {value}: {count}")
                else:
                    text_output.append(f"  {col} - {unique_count} unique values (too many to list)")
                text_output.append("")
        
        return "\n".join(text_output)
    
    def _get_numeric_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Get statistical summary of numeric data"""
        numeric_cols = df.select_dtypes(include=['number']).columns
        
        if len(numeric_cols) == 0:
            return {"message": "No numeric columns found"}
        
        summary = {}
        for col in numeric_cols:
            col_data = df[col].dropna()
            if len(col_data) > 0:
                summary[col] = {
                    "count": len(col_data),
                    "mean": float(col_data.mean()),
                    "median": float(col_data.median()),
                    "std": float(col_data.std()) if len(col_data) > 1 else 0,
                    "min": float(col_data.min()),
                    "max": float(col_data.max()),
                    "sum": float(col_data.sum())
                }
        
        return summary
    
    def _identify_key_data_patterns(self, df: pd.DataFrame) -> List[str]:
        """Identify key patterns and insights from the data"""
        insights = []
        
        # Check for potential key business metrics
        numeric_cols = df.select_dtypes(include=['number']).columns
        
        for col in numeric_cols:
            col_data = df[col].dropna()
            if len(col_data) > 0:
                # Identify columns with high values (potential revenue/cost columns)
                if col_data.max() > 10000:
                    insights.append(f"{col} contains large values (max: {col_data.max():.0f}) - likely financial metric")
                
                # Identify percentage columns
                if col_data.max() <= 1.0 and col_data.min() >= 0:
                    insights.append(f"{col} appears to be percentages or ratios (0-1 range)")
                elif col_data.max() <= 100 and col_data.min() >= 0 and 'percent' in col.lower():
                    insights.append(f"{col} appears to be percentages (0-100 range)")
        
        # Check for time-based patterns
        date_cols = df.select_dtypes(include=['datetime']).columns
        if len(date_cols) > 0:
            insights.append(f"Time-series data detected in columns: {list(date_cols)}")
        
        # Check for categorical data that might represent segments
        categorical_cols = df.select_dtypes(include=['object']).columns
        for col in categorical_cols:
            unique_count = df[col].nunique()
            if 2 <= unique_count <= 10:
                insights.append(f"{col} has {unique_count} categories - potential segmentation variable")
        
        return insights
    
    def _create_analysis_tasks(self, metrics: Dict[str, Any], sheet_name: str) -> List[str]:
        """Create specific analysis tasks based on extracted metrics"""
        tasks = []
        
        # Create tasks based on data type
        if metrics["data_summary"]["financial_metrics"]:
            tasks.append(f"Analyze financial data from {sheet_name}: {', '.join(metrics['data_summary']['financial_metrics'])}")
            
        if metrics["data_summary"]["customer_metrics"]:
            tasks.append(f"Perform customer analysis on {sheet_name}: {', '.join(metrics['data_summary']['customer_metrics'])}")
            
        if metrics["data_summary"]["operational_metrics"]:
            tasks.append(f"Evaluate operational metrics in {sheet_name}: {', '.join(metrics['data_summary']['operational_metrics'])}")
        
        return tasks
    
    def _create_comprehensive_tasks(self, all_data: Dict[str, Any]) -> List[str]:
        """Create comprehensive business analysis tasks"""
        comprehensive_tasks = [
            "Perform comprehensive ROI analysis for the proposed business case",
            "Analyze customer acquisition cost (CAC) and lifetime value (CLV) implications", 
            "Evaluate pricing strategy impact on customer segments",
            "Assess competitive positioning and market response scenarios",
            "Model financial projections with sensitivity analysis",
            "Analyze operational efficiency and process optimization opportunities",
            "Evaluate risk factors and mitigation strategies",
            "Synthesize insights into executive summary with actionable recommendations",
            "Validate analysis consistency and methodology across all findings",
            "Create strategic implementation roadmap with success metrics"
        ]
        
        return comprehensive_tasks


# ─────────────────────────────── Agent Monitor ────────────────────────────── #

class BusinessAgentMonitor:
    """Monitor for business analysis agents with business-specific metrics"""
    
    def __init__(self, session: str, agents: int, check_interval: int = 10):
        self.session = session
        self.agents = agents
        self.check_interval = check_interval
        self.agent_states = {}
        self.business_metrics = {
            "analyses_completed": 0,
            "insights_generated": 0,
            "recommendations_created": 0,
            "validation_checks": 0
        }
    
    def update_business_metrics(self, agent_id: str, metric_type: str, value: int = 1):
        """Update business-specific metrics"""
        if metric_type in self.business_metrics:
            self.business_metrics[metric_type] += value
            
    def get_agent_status_table(self) -> Table:
        """Create rich table showing agent status with business metrics"""
        table = Table(title="Business Analysis Agent Status", box=box.ROUNDED)
        
        table.add_column("Agent", style="cyan", no_wrap=True)
        table.add_column("Type", style="magenta")
        table.add_column("Status", style="green")
        table.add_column("Current Task", style="yellow", max_width=40)
        table.add_column("Analyses", style="blue", justify="right")
        table.add_column("Insights", style="green", justify="right")
        
        for agent_id, state in self.agent_states.items():
            agent_type = state.get("type", "unknown")
            status = state.get("status", "unknown")
            current_task = state.get("current_task", "idle")
            analyses = state.get("analyses_completed", 0)
            insights = state.get("insights_generated", 0)
            
            table.add_row(
                f"Agent-{agent_id}",
                agent_type,
                status,
                current_task,
                str(analyses),
                str(insights)
            )
        
        return table


# ─────────────────────────────── Main Business Analysis Farm ────────────────────────────── #

class BusinessAnalysisFarm:
    """Main orchestrator for business analysis agents"""
    
    def __init__(
        self,
        path: str,
        agents: int = 20,
        session: str = "business_agents",
        stagger: float = 10.0,
        wait_after_cc: float = 15.0,
        check_interval: int = 10,
        skip_regenerate: bool = False, 
        skip_commit: bool = False,
        auto_restart: bool = False,
        no_monitor: bool = False,
        attach: bool = False,
        prompt_file: Optional[str] = None,
        config: Optional[str] = None,
        context_threshold: int = 20,
        idle_timeout: int = 60,
        max_errors: int = 3,
        tmux_kill_on_exit: bool = True,
        tmux_mouse: bool = True,
        fast_start: bool = False,
        full_backup: bool = False,
        excel_files: Optional[List[str]] = None,
        business_context: Optional[Dict[str, Any]] = None,
        language: str = "danish",
        analysis_type: str = "business_case_development",
    ):
        # Store all parameters
        self.path = path
        self.agents = agents
        self.session = session
        self.stagger = stagger
        self.wait_after_cc = wait_after_cc
        self.check_interval = check_interval
        self.skip_regenerate = skip_regenerate
        self.skip_commit = skip_commit
        self.auto_restart = auto_restart
        self.no_monitor = no_monitor
        self.attach = attach
        self.prompt_file = prompt_file
        self.config = config
        self.context_threshold = context_threshold
        self.idle_timeout = idle_timeout
        self.max_errors = max_errors
        self.tmux_kill_on_exit = tmux_kill_on_exit
        self.tmux_mouse = tmux_mouse
        self.fast_start = fast_start
        self.full_backup = full_backup
        
        # Business analysis specific parameters
        self.excel_files = excel_files or []
        self.business_context = business_context or {}
        self.language = language
        self.analysis_type = analysis_type
        
        # Initialize pane mapping and business metrics
        self.pane_mapping: Dict[int, str] = {}
        self.business_metrics = {
            "analyses_started": 0,
            "analyses_completed": 0,
            "insights_generated": 0,
            "recommendations_created": 0
        }
        
        # Track run statistics
        self.run_start_time = datetime.now()
        self.total_analyses_completed = 0
        self.total_insights_generated = 0
        self.agent_restart_count = 0
        
        # Validate session name
        if not re.match(r"^[a-zA-Z0-9_-]+$", self.session):
            raise ValueError(
                f"Invalid tmux session name '{self.session}'. Use only letters, numbers, hyphens, and underscores."
            )
        
        # Apply config file if provided
        if config:
            self._load_config(config)
            
        # Initialize paths and files
        self.project_path = Path(self.path).expanduser().resolve()
        self.business_analysis_file = self.project_path / "business_analysis_tasks.txt"
        self.prompt_text = self._load_prompt()
        self.monitor: Optional[BusinessAgentMonitor] = None
        self.running = True
        
        # Initialize Excel processor
        self.excel_processor = ExcelProcessor(self.excel_files, self.business_context)
        
    def _load_config(self, config_path: str) -> None:
        """Load configuration from JSON file"""
        config_file = Path(config_path).expanduser().resolve()
        if not config_file.exists():
            console.print(f"[red]Config file {config_file} not found[/red]")
            return
            
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                
            # Update instance attributes from config
            for key, value in config_data.items():
                if hasattr(self, key):
                    setattr(self, key, value)
                    
            console.print(f"[green]Loaded configuration from {config_file}[/green]")
        except Exception as e:
            console.print(f"[red]Error loading config: {e}[/red]")
            
    def _load_prompt(self) -> str:
        """Load business analysis prompt template"""
        if self.prompt_file and Path(self.prompt_file).exists():
            with open(self.prompt_file, 'r', encoding='utf-8') as f:
                return f.read()
        
        # Default business analysis prompt
        return """
You are a specialized business analysis agent working as part of a multi-agent business intelligence farm.

CONTEXT:
- Language: {language}
- Analysis Type: {analysis_type}
- Business Context: {business_context}

ROLE: {agent_type}
FOCUS: {agent_focus}

TASK: Analyze the provided business data and generate insights according to your specialization.

INSTRUCTIONS:
1. Focus on your specialized area: {agent_focus}
2. Provide quantitative analysis with supporting calculations
3. Generate actionable insights and recommendations
4. Consider Danish/Nordic business context where applicable
5. Structure your response for executive consumption
6. Include confidence levels and key assumptions
7. Collaborate with other agents by sharing relevant insights

OUTPUT FORMAT:
## Analysis Summary
[Brief executive summary]

## Key Findings
[Bullet points of main insights]

## Quantitative Analysis
[Detailed calculations and metrics]

## Recommendations
[Actionable next steps]

## Confidence & Assumptions
[Assessment of analysis reliability]

Begin your analysis now.
"""
    
    def generate_business_tasks(self) -> None:
        """Generate business analysis tasks from Excel files and context"""
        console.rule("[yellow]Generating Business Analysis Tasks")
        
        if not self.excel_files:
            console.print("[yellow]No Excel files provided, using default business analysis tasks[/yellow]")
            self._create_default_tasks()
            return
            
        # Process Excel files
        processed_data = self.excel_processor.process_excel_files()
        
        # Create business analysis tasks file with full Excel data
        with open(self.business_analysis_file, 'w', encoding='utf-8') as f:
            f.write("# Business Analysis Tasks with Excel Data\n")
            f.write(f"# Generated: {datetime.now().isoformat()}\n")
            f.write(f"# Analysis Type: {self.analysis_type}\n")
            f.write(f"# Language: {self.language}\n\n")
            
            # Write business context
            f.write("## Business Context\n")
            for key, value in self.business_context.items():
                if isinstance(value, dict):
                    f.write(f"- {key}:\n")
                    for sub_key, sub_value in value.items():
                        f.write(f"  - {sub_key}: {sub_value}\n")
                else:
                    f.write(f"- {key}: {value}\n")
            f.write("\n")
            
            # Write Excel data content for agents to analyze
            f.write("## Excel Data Content\n")
            f.write("IMPORTANT: The following Excel data should be analyzed by business agents:\n\n")
            
            excel_data = processed_data.get("excel_data", {})
            for excel_file, sheets_data in excel_data.items():
                f.write(f"### File: {Path(excel_file).name}\n")
                f.write(f"Source: {excel_file}\n\n")
                
                # Get processed metrics for each sheet
                for sheet_name, df in sheets_data.items():
                    # Process this sheet to get the structured text
                    metrics = self.excel_processor._extract_business_metrics(df, sheet_name, excel_file)
                    
                    f.write(f"#### Sheet: {sheet_name}\n")
                    f.write("```\n")
                    f.write(metrics["data_content"])  # This contains the full structured data
                    f.write("\n```\n\n")
                    
                    # Add key insights
                    if metrics["data_summary"]["key_insights"]:
                        f.write("**Key Data Insights:**\n")
                        for insight in metrics["data_summary"]["key_insights"]:
                            f.write(f"- {insight}\n")
                        f.write("\n")
            
            # Write analysis tasks
            f.write("## Analysis Tasks\n")
            f.write("Each agent should analyze the Excel data above according to their specialization:\n\n")
            for i, task in enumerate(processed_data.get("business_tasks", []), 1):
                f.write(f"{i}. {task}\n")
            
            # Add data analysis instructions
            f.write("\n## Data Analysis Instructions\n")
            f.write("1. **Use the actual Excel data** provided above in your analysis\n")
            f.write("2. **Reference specific numbers** from the data tables\n")
            f.write("3. **Perform calculations** using the provided data\n")
            f.write("4. **Identify trends and patterns** in the numeric data\n")
            f.write("5. **Cross-reference data** between different sheets when relevant\n")
            f.write("6. **Validate assumptions** against the actual data provided\n")
            f.write("7. **Create projections** based on historical data patterns\n")
                
        console.print(f"[green]Generated {len(processed_data.get('business_tasks', []))} business analysis tasks with full Excel data[/green]")
        
        # Store processed data for agent access
        self.processed_excel_data = processed_data
        
    def _create_default_tasks(self) -> None:
        """Create default business analysis tasks"""
        default_tasks = [
            "Analyze the business case for implementing Click & Collect service with 25 DKK fee",
            "Evaluate customer segmentation and fee tolerance across different customer groups", 
            "Calculate unit economics and break-even analysis for the proposed fee structure",
            "Assess competitive landscape and pricing strategies in the Nordic market",
            "Model financial projections including revenue impact and cost savings",
            "Analyze operational requirements and process optimization opportunities",
            "Evaluate risk factors and scenario planning for fee implementation",
            "Generate strategic recommendations with implementation roadmap",
            "Validate analysis methodology and cross-check findings for consistency",
            "Create executive summary with key insights and actionable recommendations"
        ]
        
        with open(self.business_analysis_file, 'w', encoding='utf-8') as f:
            f.write("# Business Analysis Tasks\n")
            f.write(f"# Generated: {datetime.now().isoformat()}\n")
            f.write(f"# Analysis Type: {self.analysis_type}\n\n")
            
            for i, task in enumerate(default_tasks, 1):
                f.write(f"{i}. {task}\n")
    
    def run(self) -> None:
        """Main execution method"""
        console.print("[bold blue]🏢 Starting Business Analysis Agent Farm[/bold blue]")
        
        try:
            # Generate business analysis tasks
            self.generate_business_tasks()
            
            # Setup tmux environment
            self._setup_tmux_environment()
            
            # Launch agents
            self._launch_business_agents()
            
            # Start monitoring if enabled
            if not self.no_monitor:
                self._start_monitoring()
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down Business Analysis Farm...[/yellow]")
            self._cleanup()
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            self._cleanup()
            raise
            
    def _setup_tmux_environment(self) -> None:
        """Setup tmux session and environment"""
        console.print(f"[blue]Setting up tmux session: {self.session}[/blue]")
        ensure_session_exists(self.session, self.tmux_mouse)
        
    def _launch_business_agents(self) -> None:
        """Launch specialized business analysis agents"""
        console.print(f"[blue]Launching {self.agents} business analysis agents...[/blue]")
        
        # Distribute agents across specializations
        agent_types = list(BUSINESS_AGENT_TYPES.keys())
        agents_per_type = max(1, self.agents // len(agent_types))
        
        agent_assignments = []
        for i in range(self.agents):
            agent_type = agent_types[i % len(agent_types)]
            agent_assignments.append(agent_type)
            
        # Launch each agent with its specialization
        for i, agent_type in enumerate(agent_assignments):
            self._launch_single_agent(i, agent_type)
            if i < len(agent_assignments) - 1:
                time.sleep(self.stagger)
                
    def _launch_single_agent(self, agent_id: int, agent_type: str) -> None:
        """Launch a single specialized business analysis agent"""
        pane_name = f"agent_{agent_id}_{agent_type}"
        
        # Create specialized prompt for this agent type
        agent_config = BUSINESS_AGENT_TYPES[agent_type]
        
        # Enhanced prompt with Excel data reference
        excel_data_instruction = f"""
EXCEL DATA ACCESS:
You have access to comprehensive Excel data analysis in the file: {self.business_analysis_file}

This file contains:
- Full Excel sheet data with actual numbers and calculations
- Statistical summaries of all numeric columns  
- Categorical data analysis and insights
- Data quality assessments and key patterns

CRITICAL: You must analyze the ACTUAL DATA from the Excel sheets, not just the task descriptions.
Reference specific numbers, perform calculations, and base your analysis on the real data provided.
"""
        
        specialized_prompt = self.prompt_text.format(
            language=self.language,
            analysis_type=self.analysis_type, 
            business_context=json.dumps(self.business_context, indent=2),
            agent_type=agent_type,
            agent_focus=agent_config["prompt_focus"]
        ) + excel_data_instruction
        
        # Create tmux pane
        run(f"tmux new-window -t {self.session} -n {pane_name}")
        
        # Wait for shell prompt to be ready
        time.sleep(2)
        
        # Change to project directory first
        pane_target = f"{self.session}:{pane_name}"
        tmux_send(pane_target, f"cd {shlex.quote(str(self.project_path))}")
        time.sleep(0.5)
        
        # Launch Claude Code using the robust tmux_send function
        tmux_send(pane_target, f"claude")
        time.sleep(3)  # Wait for Claude Code to start
        
        # Send the specialized prompt using tmux_send (avoids all shell escaping issues)
        tmux_send(pane_target, specialized_prompt, enter=True)
        
        # Send command to read the business analysis file with Excel data
        time.sleep(2)  # Wait for Claude Code to process prompt
        read_data_cmd = f"Please start by reading and analyzing the file {self.business_analysis_file.name} which contains the Excel data for your specialized analysis."
        tmux_send(pane_target, read_data_cmd, enter=True)
        
        # Store pane mapping
        self.pane_mapping[agent_id] = pane_name
        
        console.print(f"[green]Launched {agent_type} agent (Agent {agent_id}) with Excel data access[/green]")
        
    def _start_monitoring(self) -> None:
        """Start monitoring business agents"""
        console.print("[blue]Starting business agent monitoring...[/blue]")
        
        self.monitor = BusinessAgentMonitor(self.session, self.agents, self.check_interval)
        
        # Monitoring loop
        while self.running:
            try:
                # Update agent states
                self._update_agent_states()
                
                # Display status
                if self.monitor:
                    table = self.monitor.get_agent_status_table()
                    console.print(table)
                    
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                break
                
    def _update_agent_states(self) -> None:
        """Update the state of all business agents"""
        # This would involve parsing tmux pane content and updating agent states
        # Implementation would check agent outputs and update business metrics
        pass
        
    def _cleanup(self) -> None:
        """Cleanup resources and tmux session"""
        console.print("[yellow]Cleaning up...[/yellow]")
        
        if self.tmux_kill_on_exit:
            try:
                run(f"tmux kill-session -t {self.session}", quiet=True)
                console.print(f"[green]Killed tmux session: {self.session}[/green]")
            except:
                pass  # Session might not exist
                
        self.running = False


# ─────────────────────────────── CLI Entry Point ──────────────────────────── #

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    path: str = typer.Option(..., "--path", help="Absolute path to project root", rich_help_panel="Required Arguments"),
    agents: int = typer.Option(
        20, "--agents", "-n", help="Number of business analysis agents", rich_help_panel="Agent Configuration"
    ),
    session: str = typer.Option(
        "business_agents", "--session", "-s", help="tmux session name", rich_help_panel="Agent Configuration"
    ),
    excel_files: str = typer.Option(
        "", "--excel-files", help="Comma-separated list of Excel files to analyze", rich_help_panel="Data Sources"
    ),
    config: Optional[str] = typer.Option(
        None, "--config", help="Load settings from JSON config file", rich_help_panel="Configuration"
    ),
    language: str = typer.Option(
        "danish", "--language", help="Analysis language (danish/english)", rich_help_panel="Localization"
    ),
    analysis_type: str = typer.Option(
        "business_case_development", "--analysis-type", help="Type of business analysis", rich_help_panel="Analysis"
    ),
    auto_restart: bool = typer.Option(
        False, "--auto-restart", help="Auto-restart agents on completion", rich_help_panel="Agent Management"
    ),
    no_monitor: bool = typer.Option(
        False, "--no-monitor", help="Disable monitoring dashboard", rich_help_panel="Agent Management"
    ),
    attach: bool = typer.Option(
        False, "--attach", help="Attach to tmux session after setup", rich_help_panel="Session Management"
    ),
) -> None:
    """
    Business Analysis Agent Farm - Multi-Agent Business Intelligence Orchestrator
    
    Orchestrates specialized business analysis agents working in parallel to analyze
    Excel data and generate comprehensive business cases and strategic insights.
    """
    
    # If a subcommand was invoked, don't run the main logic
    if ctx.invoked_subcommand is not None:
        return
        
    # Validate project path
    project_path = Path(path).expanduser().resolve()
    if not project_path.is_dir():
        console.print(f"[red]✖ {project_path} is not a directory[/red]")
        raise typer.Exit(1)
        
    # Validate agent count
    if agents < 1:
        console.print("[red]✖ Number of agents must be at least 1[/red]")
        raise typer.Exit(1)
        
    if agents > 50:
        console.print("[red]✖ Maximum 50 agents supported[/red]")
        raise typer.Exit(1)
        
    # Parse Excel files
    excel_file_list = []
    if excel_files:
        excel_file_list = [f.strip() for f in excel_files.split(",") if f.strip()]
        
    # Default business context for Kop&Kande case
    default_business_context = {
        "company": "Kop&Kande",
        "initiative": "Click & Collect Fee Implementation", 
        "proposed_fee": "25 DKK",
        "threshold": "150 DKK minimum order",
        "current_situation": "15.9% of C&C orders under 130 DKK",
        "annual_cost": "336,000 DKK",
        "average_order_size": "69 DKK ex moms",
        "market": "Nordic retail",
        "analysis_language": language
    }
    
    # Initialize and run the business analysis farm
    farm = BusinessAnalysisFarm(
        path=str(project_path),
        agents=agents,
        session=session,
        excel_files=excel_file_list,
        business_context=default_business_context,
        language=language,
        analysis_type=analysis_type,
        config=config,
        auto_restart=auto_restart,
        no_monitor=no_monitor,
        attach=attach,
    )
    
    try:
        farm.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Business Analysis Farm interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Business Analysis Farm failed: {e}[/red]")
        raise typer.Exit(1)
        
    console.print("[green]✓ Business Analysis Farm completed successfully[/green]")


if __name__ == "__main__":
    app()