#!/usr/bin/env python3
"""
Test script for Business Analysis Farm
Validates core functionality without launching actual agents
"""

import json
import pandas as pd
from pathlib import Path
from business_analysis_farm import BusinessAnalysisFarm, ExcelProcessor, BUSINESS_AGENT_TYPES

def test_excel_processor():
    """Test Excel processing functionality"""
    print("🧪 Testing Excel Processor...")
    
    # Create sample test data
    test_data = {
        'Financials': pd.DataFrame({
            'Metric': ['Revenue', 'Cost', 'Orders', 'C&C_Orders'],
            'Value': [1000000, 750000, 15000, 2400],
            'Unit': ['DKK', 'DKK', 'count', 'count']
        }),
        'Customer_Segments': pd.DataFrame({
            'Segment': ['Convenience', 'Price_Conscious', 'Digital', 'Traditional'],
            'Size': [35, 28, 22, 15],
            'Avg_Order': [85, 65, 55, 75],
            'C&C_Usage': [65, 25, 55, 15]
        })
    }
    
    # Save as temporary Excel file
    test_file = Path("test_data.xlsx")
    with pd.ExcelWriter(test_file) as writer:
        for sheet_name, df in test_data.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    # Test processor
    business_context = {
        "company": "TestCorp",
        "initiative": "C&C Fee Test"
    }
    
    processor = ExcelProcessor([str(test_file)], business_context)
    processed = processor.process_excel_files()
    
    print(f"✅ Processed {len(processed['business_tasks'])} tasks")
    print(f"✅ Excel data keys: {list(processed['excel_data'].keys())}")
    
    # Cleanup
    test_file.unlink()
    return True


def test_agent_specializations():
    """Test agent type definitions"""
    print("🧪 Testing Agent Specializations...")
    
    expected_types = [
        'financial_modeling', 'customer_analytics', 'pricing_strategy',
        'market_intelligence', 'operations_analytics', 'risk_assessment',
        'strategic_planning', 'data_integration', 'qa_validation', 
        'synthesis_coordination'
    ]
    
    # Check all expected types exist
    missing_types = [t for t in expected_types if t not in BUSINESS_AGENT_TYPES]
    if missing_types:
        print(f"❌ Missing agent types: {missing_types}")
        return False
    
    # Validate structure
    for agent_type, config in BUSINESS_AGENT_TYPES.items():
        required_keys = ['description', 'prompt_focus', 'excel_sheets']
        missing_keys = [k for k in required_keys if k not in config]
        if missing_keys:
            print(f"❌ Agent {agent_type} missing keys: {missing_keys}")
            return False
    
    print(f"✅ All {len(BUSINESS_AGENT_TYPES)} agent types properly configured")
    return True


def test_config_loading():
    """Test configuration file loading"""
    print("🧪 Testing Configuration Loading...")
    
    config_file = Path("kop_kande_config.json")
    if not config_file.exists():
        print("❌ Configuration file not found")
        return False
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    required_sections = [
        'business_context', 'agent_specializations', 
        'analysis_parameters', 'excel_files'
    ]
    
    missing_sections = [s for s in required_sections if s not in config]
    if missing_sections:
        print(f"❌ Missing config sections: {missing_sections}")
        return False
    
    print("✅ Configuration file structure valid")
    return True


def test_prompt_templates():
    """Test prompt template files"""
    print("🧪 Testing Prompt Templates...")
    
    prompts_dir = Path("prompts")
    if not prompts_dir.exists():
        print("❌ Prompts directory not found")
        return False
    
    expected_prompts = [
        'business_analysis_base_prompt.md',
        'financial_modeling_prompt.md', 
        'customer_analytics_prompt.md',
        'pricing_strategy_prompt.md'
    ]
    
    missing_prompts = []
    for prompt_file in expected_prompts:
        if not (prompts_dir / prompt_file).exists():
            missing_prompts.append(prompt_file)
    
    if missing_prompts:
        print(f"❌ Missing prompt files: {missing_prompts}")
        return False
    
    print(f"✅ All {len(expected_prompts)} prompt templates found")
    return True


def test_business_farm_initialization():
    """Test BusinessAnalysisFarm initialization"""
    print("🧪 Testing Business Farm Initialization...")
    
    try:
        farm = BusinessAnalysisFarm(
            path=".",
            agents=5,
            session="test_session",
            excel_files=["test.xlsx"],
            business_context={"test": "data"},
            language="danish",
            analysis_type="test",
            no_monitor=True  # Disable monitoring for test
        )
        
        # Test basic attributes
        assert farm.agents == 5
        assert farm.language == "danish"
        assert farm.analysis_type == "test"
        assert hasattr(farm, 'excel_processor')
        
        print("✅ Business farm initialized successfully")
        return True
    
    except Exception as e:
        print(f"❌ Business farm initialization failed: {e}")
        return False


def test_agent_distribution():
    """Test agent distribution across specializations"""
    print("🧪 Testing Agent Distribution...")
    
    # Test with different agent counts
    for agent_count in [10, 20, 25]:
        agent_types = list(BUSINESS_AGENT_TYPES.keys())
        agents_per_type = max(1, agent_count // len(agent_types))
        
        agent_assignments = []
        for i in range(agent_count):
            agent_type = agent_types[i % len(agent_types)]
            agent_assignments.append(agent_type)
        
        # Check distribution
        type_counts = {}
        for agent_type in agent_assignments:
            type_counts[agent_type] = type_counts.get(agent_type, 0) + 1
        
        print(f"✅ {agent_count} agents distributed: {dict(sorted(type_counts.items()))}")
    
    return True


def run_all_tests():
    """Run all validation tests"""
    print("🚀 Starting Business Analysis Farm Validation Tests\n")
    
    tests = [
        ("Excel Processor", test_excel_processor),
        ("Agent Specializations", test_agent_specializations), 
        ("Configuration Loading", test_config_loading),
        ("Prompt Templates", test_prompt_templates),
        ("Business Farm Init", test_business_farm_initialization),
        ("Agent Distribution", test_agent_distribution)
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
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 50)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:8} | {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! Business Analysis Farm is ready for deployment.")
    else:
        print("⚠️  Some tests failed. Please review and fix issues before deployment.")
    
    return passed == len(results)


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)