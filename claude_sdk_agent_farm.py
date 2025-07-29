#!/usr/bin/env python3
"""
Claude Code SDK Agent Farm
Replacement for tmux-based system with direct SDK streaming
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import tempfile
from dataclasses import dataclass

# Try to import Claude Code SDK - if not available, fall back to subprocess
try:
    from claude_code import query, ClaudeCodeOptions, Message
    SDK_AVAILABLE = True
    print("✅ Claude Code SDK available - using direct streaming")
except ImportError:
    SDK_AVAILABLE = False
    print("⚠️  Claude Code SDK not available - will use subprocess fallback")
    
    # Mock Message class for fallback
    class Message:
        def __init__(self, content):
            self.content = content

@dataclass
class AgentConfig:
    """Configuration for a business analysis agent"""
    agent_id: int
    agent_type: str
    description: str
    prompt_focus: str
    excel_sheets: List[str]

@dataclass 
class StreamingMessage:
    """Message from streaming agent"""
    agent_id: int
    agent_type: str
    message_type: str  # "thinking", "progress", "result", "error"
    content: str
    timestamp: datetime

class ClaudeSDKAgentFarm:
    """Business Analysis Agent Farm using Claude Code SDK"""
    
    def __init__(self, 
                 session_id: str,
                 excel_files: List[str] = None,
                 business_context: Dict[str, Any] = None,
                 language: str = "danish",
                 analysis_type: str = "business_case_development",
                 agents: int = 10):
        self.session_id = session_id
        self.excel_files = excel_files or []
        self.business_context = business_context or {}
        self.language = language
        self.analysis_type = analysis_type
        self.num_agents = agents
        
        # Agent configurations (from original business_analysis_farm.py)
        self.agent_configs = self._create_agent_configs()
        
        # Streaming callbacks
        self.message_callback = None
        self.progress_callback = None
        
    def _create_agent_configs(self) -> List[AgentConfig]:
        """Create agent configurations matching original system"""
        configs = [
            AgentConfig(0, "financial_modeling", 
                       "Financial analysis, ROI calculations, and cost-benefit modeling",
                       "financial modeling, ROI analysis, cost-benefit calculations",
                       ["financial", "costs", "revenue", "roi"]),
            
            AgentConfig(1, "customer_analytics",
                       "Customer behavior analysis, segmentation, and lifecycle modeling", 
                       "customer analytics, behavior patterns, segmentation analysis",
                       ["customers", "behavior", "segments", "lifecycle"]),
            
            AgentConfig(2, "pricing_strategy",
                       "Pricing optimization, competitive analysis, and revenue modeling",
                       "pricing strategy, competitive analysis, revenue optimization", 
                       ["pricing", "competition", "revenue", "market"]),
            
            AgentConfig(3, "market_intelligence", 
                       "Market research, competitive intelligence, and trend analysis",
                       "market intelligence, competitive research, trend analysis",
                       ["market", "competitors", "trends", "intelligence"]),
            
            AgentConfig(4, "operations_analytics",
                       "Operational efficiency, process optimization, and performance metrics",
                       "operations analytics, process optimization, efficiency metrics",
                       ["operations", "processes", "efficiency", "performance"]),
            
            AgentConfig(5, "risk_assessment",
                       "Risk analysis, mitigation strategies, and impact assessment", 
                       "risk assessment, mitigation strategies, impact analysis",
                       ["risk", "mitigation", "impact", "assessment"]),
            
            AgentConfig(6, "strategic_planning",
                       "Strategic analysis, planning, and implementation roadmaps",
                       "strategic planning, implementation roadmaps, strategic analysis", 
                       ["strategy", "planning", "roadmap", "implementation"]),
            
            AgentConfig(7, "data_integration",
                       "Data analysis, integration, and insight generation",
                       "data integration, analysis synthesis, insight generation",
                       ["data", "integration", "insights", "analysis"]),
            
            AgentConfig(8, "qa_validation", 
                       "Quality assurance, validation, and consistency checking",
                       "quality assurance, validation, consistency checking",
                       ["quality", "validation", "consistency", "review"]),
            
            AgentConfig(9, "synthesis_coordination",
                       "Analysis synthesis, coordination, and comprehensive reporting",
                       "synthesis coordination, comprehensive reporting, final integration",
                       ["synthesis", "coordination", "reporting", "integration"])
        ]
        return configs[:self.num_agents]
    
    def set_message_callback(self, callback):
        """Set callback for streaming messages"""
        self.message_callback = callback
        
    def set_progress_callback(self, callback):
        """Set callback for progress updates"""
        self.progress_callback = callback
    
    async def _send_message(self, message: StreamingMessage):
        """Send message via callback if available"""
        if self.message_callback:
            await self.message_callback(message)
    
    async def _send_progress(self, active_agents: int, status: str):
        """Send progress update via callback if available"""
        if self.progress_callback:
            await self.progress_callback(active_agents, status)
    
    def _create_agent_prompt(self, config: AgentConfig) -> str:
        """Create specialized prompt for agent (from original system)"""
        
        # Base business context
        context_str = f"""
Business Context:
- Company: {self.business_context.get('company', 'Client Company')}
- Initiative: {self.business_context.get('initiative', 'Business Analysis')}
- Language: {self.language}
- Analysis Type: {self.analysis_type}
"""
        
        # Excel file context
        excel_context = ""
        if self.excel_files:
            excel_context = f"\nExcel Files Available: {', '.join(self.excel_files)}"
        
        # Agent-specific prompt
        agent_prompt = f"""
You are a specialized {config.agent_type} business analyst. Your expertise is in {config.description}.

{context_str}{excel_context}

Focus Areas: {config.prompt_focus}
Relevant Data Sheets: {', '.join(config.excel_sheets)}

Instructions:
1. Analyze the provided business data with focus on {config.prompt_focus}
2. Generate insights specific to {config.agent_type}
3. Provide actionable recommendations
4. Present findings in {self.language}
5. Maintain professional business analysis standards

Begin your analysis focusing on {config.prompt_focus}:
"""
        return agent_prompt.strip()
    
    async def _run_sdk_agent(self, config: AgentConfig) -> List[Message]:
        """Run agent using Claude Code SDK with streaming"""
        if not SDK_AVAILABLE:
            raise RuntimeError("Claude Code SDK not available")
        
        prompt = self._create_agent_prompt(config)
        messages = []
        
        await self._send_message(StreamingMessage(
            agent_id=config.agent_id,
            agent_type=config.agent_type,
            message_type="progress",
            content=f"🟢 Starting {config.agent_type} analysis...",
            timestamp=datetime.now()
        ))
        
        try:
            # Stream messages from Claude Code SDK
            async for message in query(
                prompt=prompt,
                options=ClaudeCodeOptions(max_turns=3)
            ):
                messages.append(message)
                
                # Stream each message chunk
                await self._send_message(StreamingMessage(
                    agent_id=config.agent_id,
                    agent_type=config.agent_type,
                    message_type="thinking",
                    content=str(message.content) if hasattr(message, 'content') else str(message),
                    timestamp=datetime.now()
                ))
                
        except Exception as e:
            await self._send_message(StreamingMessage(
                agent_id=config.agent_id,
                agent_type=config.agent_type,
                message_type="error",
                content=f"❌ Error in {config.agent_type}: {str(e)}",
                timestamp=datetime.now()
            ))
            
        await self._send_message(StreamingMessage(
            agent_id=config.agent_id,
            agent_type=config.agent_type,
            message_type="result",
            content=f"✅ {config.agent_type} analysis completed",
            timestamp=datetime.now()
        ))
        
        return messages
    
    async def _run_subprocess_agent(self, config: AgentConfig) -> str:
        """Fallback: Run agent using subprocess with streaming"""
        import subprocess
        
        prompt = self._create_agent_prompt(config)
        
        await self._send_message(StreamingMessage(
            agent_id=config.agent_id,
            agent_type=config.agent_type,
            message_type="progress",
            content=f"🟢 Starting {config.agent_type} analysis (subprocess)...",  
            timestamp=datetime.now()
        ))
        
        try:
            # Use subprocess to run Claude CLI with streaming
            proc = await asyncio.create_subprocess_exec(
                'claude', '--output-format', 'stream-json', '--verbose',
                '-p', prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            output_lines = []
            
            # Stream output line by line
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                    
                line_text = line.decode().strip()
                output_lines.append(line_text)
                
                # Stream line immediately
                await self._send_message(StreamingMessage(
                    agent_id=config.agent_id,
                    agent_type=config.agent_type,
                    message_type="thinking",
                    content=line_text,
                    timestamp=datetime.now()
                ))
            
            await proc.wait()
            result = '\n'.join(output_lines)
            
        except Exception as e:
            result = f"Error: {str(e)}"
            await self._send_message(StreamingMessage(
                agent_id=config.agent_id,
                agent_type=config.agent_type,
                message_type="error",
                content=f"❌ Error in {config.agent_type}: {str(e)}",
                timestamp=datetime.now()
            ))
        
        await self._send_message(StreamingMessage(
            agent_id=config.agent_id,
            agent_type=config.agent_type,
            message_type="result",
            content=f"✅ {config.agent_type} analysis completed",
            timestamp=datetime.now()
        ))
        
        return result
    
    async def run_analysis(self) -> Dict[str, Any]:
        """Run all agents concurrently with streaming"""
        
        print(f"🏢 Starting Claude SDK Business Analysis Agent Farm")
        print(f"📊 Session: {self.session_id}")
        print(f"🤖 Agents: {self.num_agents}")
        print(f"📁 Excel files: {len(self.excel_files)}")
        
        await self._send_progress(0, "starting")
        
        # Run all agents concurrently
        if SDK_AVAILABLE:
            tasks = [self._run_sdk_agent(config) for config in self.agent_configs]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            tasks = [self._run_subprocess_agent(config) for config in self.agent_configs]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        await self._send_progress(0, "completed")
        
        # Compile results
        analysis_results = {}
        for i, (config, result) in enumerate(zip(self.agent_configs, results)):
            if isinstance(result, Exception):
                analysis_results[config.agent_type] = f"Error: {str(result)}"
            else:
                analysis_results[config.agent_type] = result
                
        return {
            "session_id": self.session_id,
            "status": "completed",
            "agents": len(self.agent_configs),
            "results": analysis_results,
            "timestamp": datetime.now().isoformat()
        }

# Test function
async def test_claude_sdk_farm():
    """Test the Claude SDK Agent Farm"""
    
    # Create test farm
    farm = ClaudeSDKAgentFarm(
        session_id="test_session_123",
        excel_files=["test_data.xlsx"],
        business_context={
            "company": "Test Company",
            "initiative": "SDK Test Analysis"
        },
        agents=3  # Test with fewer agents
    )
    
    # Set up message handler
    async def handle_message(message: StreamingMessage):
        print(f"[{message.agent_type}] {message.message_type}: {message.content}")
    
    async def handle_progress(active_agents: int, status: str):
        print(f"Progress: {active_agents} agents active, status: {status}")
    
    farm.set_message_callback(handle_message)
    farm.set_progress_callback(handle_progress)
    
    # Run analysis
    results = await farm.run_analysis()
    print("Final results:", results)

if __name__ == "__main__":
    # Test the system
    asyncio.run(test_claude_sdk_farm())