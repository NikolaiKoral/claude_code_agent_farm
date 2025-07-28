#!/usr/bin/env python3
"""
Simple test for Business Analysis Farm - no external dependencies
"""

import json
from pathlib import Path

def test_file_structure():
    """Test that all required files exist"""
    print("🧪 Testing File Structure...")
    
    required_files = [
        "business_analysis_farm.py",
        "kop_kande_config.json", 
        "prompts/business_analysis_base_prompt.md",
        "prompts/financial_modeling_prompt.md",
        "prompts/customer_analytics_prompt.md",
        "prompts/pricing_strategy_prompt.md"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print(f"❌ Missing files: {missing_files}")
        return False
    
    print(f"✅ All {len(required_files)} required files found")
    return True


def test_config_structure():
    """Test configuration file structure"""
    print("🧪 Testing Configuration Structure...")
    
    config_file = Path("kop_kande_config.json")
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        required_keys = [
            'business_context', 'agent_specializations',
            'excel_files', 'analysis_type', 'language'
        ]
        
        missing_keys = [k for k in required_keys if k not in config]
        if missing_keys:
            print(f"❌ Missing config keys: {missing_keys}")
            return False
        
        # Test agent specializations sum
        total_agents = sum(config['agent_specializations'].values())
        if total_agents != config.get('agents', 25):
            print(f"⚠️  Agent specialization total ({total_agents}) doesn't match agent count")
        
        print("✅ Configuration structure valid")
        return True
        
    except Exception as e:
        print(f"❌ Config validation failed: {e}")
        return False


def test_agent_types():
    """Test agent type definitions from main file"""
    print("🧪 Testing Agent Types...")
    
    # Read the business farm file to extract agent types
    try:
        with open("business_analysis_farm.py", 'r') as f:
            content = f.read()
        
        # Check for BUSINESS_AGENT_TYPES definition
        if "BUSINESS_AGENT_TYPES" not in content:
            print("❌ BUSINESS_AGENT_TYPES not found in main file")
            return False
        
        # Check for key agent types
        expected_types = [
            'financial_modeling', 'customer_analytics', 'pricing_strategy',
            'market_intelligence', 'operations_analytics', 'risk_assessment'
        ]
        
        missing_types = [t for t in expected_types if t not in content]
        if missing_types:
            print(f"❌ Missing agent types in code: {missing_types}")
            return False
        
        print(f"✅ Agent types properly defined")
        return True
        
    except Exception as e:
        print(f"❌ Agent type validation failed: {e}")
        return False


def test_prompt_content():
    """Test prompt file content"""
    print("🧪 Testing Prompt Content...")
    
    prompt_files = [
        "prompts/business_analysis_base_prompt.md",
        "prompts/financial_modeling_prompt.md"
    ]
    
    for prompt_file in prompt_files:
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for Danish content
            if "danish" not in content.lower() and "dansk" not in content.lower():
                print(f"⚠️  {prompt_file} may not contain Danish localization")
            
            # Check for business context placeholders
            if "{" not in content or "}" not in content:
                print(f"⚠️  {prompt_file} may not contain templating placeholders")
            
        except Exception as e:
            print(f"❌ Error reading {prompt_file}: {e}")
            return False
    
    print("✅ Prompt files validated")
    return True


def test_cli_structure():
    """Test CLI structure in main file"""
    print("🧪 Testing CLI Structure...")
    
    try:
        with open("business_analysis_farm.py", 'r') as f:
            content = f.read()
        
        # Check for key CLI components
        cli_components = [
            "@app.callback", "def main", "typer.Option",
            "excel_files", "BusinessAnalysisFarm"
        ]
        
        missing_components = [c for c in cli_components if c not in content]
        if missing_components:
            print(f"❌ Missing CLI components: {missing_components}")
            return False
        
        print("✅ CLI structure validated")
        return True
        
    except Exception as e:
        print(f"❌ CLI validation failed: {e}")
        return False


def run_simple_tests():
    """Run all simple validation tests"""
    print("🚀 Running Simple Business Analysis Farm Tests\n")
    
    tests = [
        ("File Structure", test_file_structure),
        ("Configuration", test_config_structure),
        ("Agent Types", test_agent_types),
        ("Prompt Content", test_prompt_content),
        ("CLI Structure", test_cli_structure)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            print()
        except Exception as e:
            print(f"❌ {test_name} failed with error: {e}\n")
            results.append((test_name, False))
    
    # Summary
    print("📊 TEST RESULTS")
    print("=" * 30)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} | {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 Basic validation passed!")
        print("\n📋 Next Steps:")
        print("1. Install required dependencies: pip install pandas openpyxl typer rich")
        print("2. Test with actual Excel files")
        print("3. Launch business analysis farm")
    else:
        print("⚠️  Some tests failed. Please review issues.")
    
    return passed == len(results)


if __name__ == "__main__":
    success = run_simple_tests()
    exit(0 if success else 1)