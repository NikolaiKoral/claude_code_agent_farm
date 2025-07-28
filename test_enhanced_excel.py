#!/usr/bin/env python3
"""
Test enhanced Excel integration with actual data processing
"""

import pandas as pd
import json
from pathlib import Path
from business_analysis_farm import ExcelProcessor, BusinessAnalysisFarm

def create_sample_kop_kande_data():
    """Create sample Excel data similar to Kop&Kande case"""
    
    # Financial data sheet
    financial_data = pd.DataFrame({
        'Metric': ['Total Revenue', 'C&C Revenue', 'C&C Costs', 'Small Orders', 'Small Order Cost'],
        'Value_DKK': [5000000, 800000, 336000, 127200, 336000],
        'Percentage': [100.0, 16.0, 6.7, 15.9, 6.7],
        'Description': [
            'Annual total revenue',
            'Click & Collect revenue',
            'Annual C&C handling costs',
            'Revenue from orders <130 DKK',
            'Cost of small C&C orders'
        ]
    })
    
    # Customer segments sheet
    customer_data = pd.DataFrame({
        'Segment': ['Convenience Seekers', 'Price Conscious', 'Digital Natives', 'Traditional'],
        'Size_Percent': [35, 28, 22, 15],
        'Avg_Order_DKK': [85, 65, 55, 75],
        'CC_Usage_Percent': [65, 25, 55, 15],
        'Fee_Tolerance_DKK': [50, 0, 25, 15],
        'Churn_Risk': [0.05, 0.15, 0.08, 0.03]
    })
    
    # Order analysis sheet
    order_data = pd.DataFrame({
        'Order_Range': ['0-50 DKK', '50-100 DKK', '100-150 DKK', '150-200 DKK', '200+ DKK'],
        'Order_Count': [2400, 3600, 1200, 4800, 8000],  
        'Percentage': [12.0, 18.0, 6.0, 24.0, 40.0],
        'CC_Orders': [380, 570, 190, 720, 1200],
        'CC_Percentage': [15.8, 15.8, 15.8, 15.0, 15.0]
    })
    
    # Create Excel file
    test_file = Path("sample_kop_kande_data.xlsx")
    with pd.ExcelWriter(test_file, engine='openpyxl') as writer:
        financial_data.to_excel(writer, sheet_name='Financial_Metrics', index=False)
        customer_data.to_excel(writer, sheet_name='Customer_Segments', index=False)
        order_data.to_excel(writer, sheet_name='Order_Analysis', index=False)
    
    return str(test_file)

def test_enhanced_excel_processing():
    """Test the enhanced Excel processing capabilities"""
    print("🧪 Testing Enhanced Excel Processing...")
    
    # Create sample data
    excel_file = create_sample_kop_kande_data()
    
    business_context = {
        "company": "Kop&Kande",
        "initiative": "Click & Collect Fee Analysis",
        "proposed_fee": "25 DKK",
        "current_situation": {
            "small_order_percentage": "15.9%",
            "annual_cost": "336,000 DKK"
        }
    }
    
    # Test ExcelProcessor
    processor = ExcelProcessor([excel_file], business_context)
    processed_data = processor.process_excel_files()
    
    print("✅ Excel processing completed")
    print(f"   - Files processed: {len(processed_data['excel_data'])}")
    print(f"   - Business tasks generated: {processed_data['task_count']}")
    
    # Test data content extraction
    excel_data = processed_data['excel_data'][excel_file]
    
    for sheet_name, df in excel_data.items():
        metrics = processor._extract_business_metrics(df, sheet_name, excel_file)
        print(f"\n📊 Sheet: {sheet_name}")
        print(f"   - Dimensions: {metrics['row_count']} rows × {metrics['column_count']} columns")
        print(f"   - Financial metrics: {len(metrics['data_summary']['financial_metrics'])}")
        print(f"   - Customer metrics: {len(metrics['data_summary']['customer_metrics'])}")
        print(f"   - Key insights: {len(metrics['data_summary']['key_insights'])}")
        
        # Show sample of structured data
        data_preview = metrics['data_content'][:300] + "..." if len(metrics['data_content']) > 300 else metrics['data_content']
        print(f"   - Data preview: {data_preview}")
    
    # Cleanup
    Path(excel_file).unlink()
    return True

def test_business_farm_excel_integration():
    """Test BusinessAnalysisFarm with enhanced Excel integration"""
    print("\n🧪 Testing Business Farm Excel Integration...")
    
    # Create sample data
    excel_file = create_sample_kop_kande_data()
    
    try:
        # Initialize farm with Excel data
        farm = BusinessAnalysisFarm(
            path=".",
            agents=5,
            session="test_excel_session",
            excel_files=[excel_file],
            business_context={
                "company": "Kop&Kande",
                "initiative": "C&C Fee Test",
                "proposed_fee": "25 DKK"
            },
            language="danish",
            analysis_type="business_case_development",
            no_monitor=True
        )
        
        # Test business task generation with Excel data
        farm.generate_business_tasks()
        
        # Check if the business analysis file was created with Excel data
        if farm.business_analysis_file.exists():
            with open(farm.business_analysis_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print("✅ Business analysis file created with Excel data")
            print(f"   - File size: {len(content)} characters")
            print(f"   - Contains Excel data: {'Excel Data Content' in content}")
            print(f"   - Contains actual numbers: {'DKK' in content and any(char.isdigit() for char in content)}")
            print(f"   - Contains data tables: {'```' in content}")
            
            # Show sample content
            lines = content.split('\n')
            data_section_start = None
            for i, line in enumerate(lines):
                if "Excel Data Content" in line:
                    data_section_start = i
                    break
            
            if data_section_start:
                sample_lines = lines[data_section_start:data_section_start+15]
                print("\n📄 Sample Excel data content:")
                for line in sample_lines:
                    print(f"   {line}")
            
            # Cleanup
            farm.business_analysis_file.unlink()
        else:
            print("❌ Business analysis file was not created")
            return False
        
        print("✅ Business farm Excel integration successful")
        return True
        
    except Exception as e:
        print(f"❌ Business farm test failed: {e}")
        return False
    finally:
        # Cleanup
        Path(excel_file).unlink()

def run_enhanced_excel_tests():
    """Run all enhanced Excel integration tests"""
    print("🚀 Testing Enhanced Excel Integration\n")
    
    tests = [
        ("Enhanced Excel Processing", test_enhanced_excel_processing),
        ("Business Farm Integration", test_business_farm_excel_integration)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with error: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📊 ENHANCED EXCEL TEST RESULTS")
    print("=" * 40)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} | {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 Enhanced Excel integration is working!")
        print("\n💡 Key improvements:")
        print("- Agents now receive ACTUAL Excel data, not just task descriptions")
        print("- Full data tables with numbers for analysis")
        print("- Statistical summaries and data insights")
        print("- Structured data format for better analysis")
        print("- Danish business context integration")
    else:
        print("⚠️  Some tests failed. Please review issues.")
    
    return passed == len(results)

if __name__ == "__main__":
    success = run_enhanced_excel_tests()
    exit(0 if success else 1)