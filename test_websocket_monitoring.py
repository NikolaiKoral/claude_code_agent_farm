#!/usr/bin/env python3
"""
Test script to verify WebSocket monitoring functionality
"""
import asyncio
import subprocess
from datetime import datetime

async def test_tmux_monitoring():
    """Test tmux session monitoring logic"""
    print("🔍 Testing tmux session monitoring...")
    
    # List all business agent sessions
    result = subprocess.run(
        ["tmux", "list-sessions"], 
        capture_output=True, text=True, check=False
    )
    
    if result.returncode == 0:
        sessions = [line for line in result.stdout.split('\n') if 'business_agents_' in line]
        print(f"Found {len(sessions)} business agent sessions:")
        for session in sessions:
            print(f"  - {session}")
            
        if sessions:
            # Test monitoring for first session
            session_line = sessions[0]
            session_name = session_line.split(':')[0]
            print(f"\n📊 Testing monitoring for session: {session_name}")
            
            # List windows in session
            result = subprocess.run(
                ["tmux", "list-windows", "-t", session_name], 
                capture_output=True, text=True, check=False
            )
            
            if result.returncode == 0:
                windows = result.stdout.strip().split('\n') if result.stdout.strip() else []
                agent_windows = [w for w in windows if 'agent_' in w]
                
                print(f"Found {len(agent_windows)} agent windows:")
                for window in agent_windows:
                    print(f"  - {window}")
                    
                print(f"\n✅ Monitoring test successful: {len(agent_windows)} active agents")
                return True
            else:
                print(f"❌ Failed to list windows: {result.stderr}")
        else:
            print("❌ No business agent sessions found")
    else:
        print(f"❌ Failed to list tmux sessions: {result.stderr}")
    
    return False

if __name__ == "__main__":
    asyncio.run(test_tmux_monitoring())