#!/usr/bin/env python3
"""
Script to validate OSCAR agent configurations using the validation utilities.
This script validates both template and extracted agent configurations.
"""

import sys
from pathlib import Path

# Add the utils directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))

from agent_config_validator import AgentConfigValidator


def main():
    """Validate OSCAR agent configurations."""
    print("OSCAR Agent Configuration Validator")
    print("=" * 40)
    
    # Initialize validator
    validator = AgentConfigValidator()
    
    # Find configuration files
    configs_dir = Path("cdk/agents/configs")
    if not configs_dir.exists():
        print(f"✗ Configuration directory not found: {configs_dir}")
        return 1
    
    config_files = list(configs_dir.glob("*.json"))
    if not config_files:
        print(f"✗ No configuration files found in: {configs_dir}")
        return 1
    
    print(f"Found {len(config_files)} configuration files:")
    for config_file in config_files:
        print(f"  - {config_file.name}")
    print()
    
    # Validate all configurations
    print("Validating configurations...")
    print("-" * 30)
    
    config_file_paths = [str(config_file) for config_file in config_files]
    results = validator.validate_multiple_configs(config_file_paths)
    
    # Generate and display report
    report = validator.generate_validation_report(results)
    print(report)
    
    # Summary
    total_configs = len(results)
    valid_configs = sum(1 for result in results.values() if result.is_valid)
    configs_with_errors = sum(1 for result in results.values() if result.has_errors)
    
    print("\nValidation Summary:")
    print(f"  Total configurations: {total_configs}")
    print(f"  Valid configurations: {valid_configs}")
    print(f"  Configurations with errors: {configs_with_errors}")
    
    if valid_configs == total_configs:
        print("✓ All configurations are valid!")
        return 0
    else:
        print("⚠ Some configurations have issues. See details above.")
        return 1


if __name__ == "__main__":
    exit(main())