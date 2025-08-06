#!/usr/bin/env python3

import boto3
import json
from dotenv import load_dotenv

load_dotenv()

def test_individual_agent(agent_id, agent_name, alias_id="TSTALIASID"):
    """Test an individual agent directly"""
    print(f"Testing {agent_name} (ID: {agent_id})...")
    
    try:
        bedrock_agent = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
        
        response = bedrock_agent.invoke_agent(
            agentId=agent_id,
            agentAliasId=alias_id,
            sessionId=f'test-{agent_name}-session',
            inputText='Show me metrics data'
        )
        
        # Process streaming response
        result = ""
        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    result += chunk['bytes'].decode('utf-8')
        
        print(f"✅ {agent_name}: SUCCESS")
        print(f"Response preview: {result[:200]}...")
        return True
        
    except Exception as e:
        print(f"❌ {agent_name}: FAILED")
        print(f"Error: {e}")
        return False

def main():
    print("🧪 Testing Individual V2 Agents")
    print("================================")
    
    agents = [
        ("YXSZJ659S7", "TestAnalyzer"),
        ("0NBATJIVCH", "BuildAnalyzer"), 
        ("4FCARBPEYB", "ReleaseAnalyzer"),
        ("BIHPD6OLO0", "DeploymentAnalyzer")
    ]
    
    results = {}
    for agent_id, agent_name in agents:
        results[agent_name] = test_individual_agent(agent_id, agent_name)
        print("")
    
    print("📋 Summary")
    print("==========")
    success_count = sum(results.values())
    print(f"✅ Successful: {success_count}/{len(agents)}")
    print(f"❌ Failed: {len(agents) - success_count}/{len(agents)}")
    
    if success_count == len(agents):
        print("\n🎉 All individual agents working!")
        print("The issue is likely in the supervisor agent's response format expectations.")
    else:
        print("\n⚠️ Some agents still have issues - check the errors above.")

if __name__ == "__main__":
    main()