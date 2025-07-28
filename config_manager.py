#!/usr/bin/env python3
"""
Configuration Manager for Business Analysis Agent Farm
Handles template substitution and dynamic configuration generation
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

class ConfigurationManager:
    """Manages configuration templates and variable substitution for business analysis"""
    
    def __init__(self, config_dir: str = "configs"):
        self.config_dir = Path(config_dir)
        self.templates = {}
        self.load_templates()
    
    def load_templates(self):
        """Load all configuration templates from the configs directory"""
        template_files = self.config_dir.glob("*_config.json")
        
        for template_file in template_files:
            template_name = template_file.stem.replace("_config", "")
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    self.templates[template_name] = json.load(f)
                print(f"✓ Loaded template: {template_name}")
            except Exception as e:
                print(f"✗ Error loading template {template_name}: {e}")
    
    def get_available_templates(self) -> List[str]:
        """Get list of available configuration templates"""
        return list(self.templates.keys())
    
    def get_template_variables(self, template_name: str) -> List[str]:
        """Extract all template variables from a configuration"""
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
        
        template_str = json.dumps(self.templates[template_name])
        variables = re.findall(r'{{([^}]+)}}', template_str)
        return list(set(variables))  # Remove duplicates
    
    def create_configuration(self, 
                           template_name: str, 
                           variables: Dict[str, Any],
                           output_path: Optional[str] = None) -> Dict[str, Any]:
        """Create a configuration by substituting variables in template"""
        
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
        
        # Convert template to string for substitution
        template_str = json.dumps(self.templates[template_name], indent=2)
        
        # Substitute variables
        for var_name, var_value in variables.items():
            placeholder = f"{{{{{var_name}}}}}"
            template_str = template_str.replace(placeholder, str(var_value))
        
        # Check for unsubstituted variables
        remaining_vars = re.findall(r'{{([^}]+)}}', template_str)
        if remaining_vars:
            print(f"Warning: Unsubstituted variables found: {remaining_vars}")
        
        # Convert back to dict
        config = json.loads(template_str)
        
        # Save to file if path provided
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"✓ Configuration saved to: {output_path}")
        
        return config
    
    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        """Validate a configuration for required fields"""
        required_fields = [
            "analysis_type",
            "business_context",
            "agent_specializations"
        ]
        
        for field in required_fields:
            if field not in config:
                print(f"✗ Missing required field: {field}")
                return False
        
        # Validate agent specializations sum to total agents
        total_agents = config.get("agents", 0)
        specialization_sum = sum(config["agent_specializations"].values())
        
        if specialization_sum != total_agents:
            print(f"✗ Agent specializations ({specialization_sum}) don't sum to total agents ({total_agents})")
            return False
        
        print("✓ Configuration validation passed")
        return True
    
    def create_quick_config(self, 
                          template_name: str,
                          company: str,
                          analysis_focus: str,
                          language: str = "english") -> Dict[str, Any]:
        """Create a quick configuration with minimal input"""
        
        # Common variable mappings based on template type
        common_vars = {
            "COMPANY_NAME": company,
            "OUTPUT_LANGUAGE": language,
            "USER_REQUEST": f"Analyze {analysis_focus} for strategic decision-making",
            "EXPECTED_OUTCOME": f"Data-driven insights and recommendations for {analysis_focus}"
        }
        
        # Template-specific defaults
        if template_name == "market_entry":
            common_vars.update({
                "MARKET_NAME": analysis_focus,
                "INDUSTRY_TYPE": "Technology/Services",
                "BRAND_POSITIONING": "Premium quality and innovation",
                "TARGET_CUSTOMERS": "Business professionals and consumers",
                "CURRENT_MARKETS": "Domestic market",
                "UNIQUE_VALUE_PROPOSITION": "Superior quality and customer service"
            })
        
        elif template_name == "product_launch":
            common_vars.update({
                "PRODUCT_NAME": analysis_focus,
                "INDUSTRY_TYPE": "Consumer Products",
                "BRAND_POSITIONING": "Quality and innovation leader",
                "TARGET_CUSTOMERS": "Target demographic consumers",
                "DISTRIBUTION_CHANNELS": "Multi-channel distribution"
            })
        
        elif template_name == "pricing_optimization":
            common_vars.update({
                "PRODUCT_SERVICE": analysis_focus,
                "INDUSTRY_TYPE": "Service Industry",
                "BRAND_POSITIONING": "Premium service provider",
                "TARGET_CUSTOMERS": "Price-conscious and value-seeking customers",
                "CURRENT_PRICING_MODEL": "Fixed pricing structure"
            })
        
        return self.create_configuration(template_name, common_vars)


def main():
    """Example usage of ConfigurationManager"""
    config_manager = ConfigurationManager()
    
    print("Available templates:")
    for template in config_manager.get_available_templates():
        print(f"  - {template}")
    
    # Example: Create a market entry configuration
    variables = {
        "COMPANY_NAME": "TechCorp",
        "MARKET_NAME": "European Union",
        "INDUSTRY_TYPE": "Software as a Service",
        "BRAND_POSITIONING": "Innovative cloud solutions provider",
        "TARGET_CUSTOMERS": "Small to medium businesses",
        "CURRENT_MARKETS": "North American market",
        "UNIQUE_VALUE_PROPOSITION": "AI-powered business automation",
        "OUTPUT_LANGUAGE": "english",
        "USER_REQUEST": "Should we expand into the EU market?",
        "EXPECTED_OUTCOME": "Go/No-Go decision with financial projections"
    }
    
    config = config_manager.create_configuration(
        "market_entry", 
        variables, 
        "configs/techcorp_eu_entry.json"
    )
    
    # Validate the configuration
    config_manager.validate_configuration(config)


if __name__ == "__main__":
    main()