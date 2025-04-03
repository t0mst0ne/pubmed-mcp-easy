#!/usr/bin/env python3
"""
Setup script for PubMed MCP Server API key and email configuration.
This script helps users set up their NCBI API key and email for the PubMed MCP Server.
"""

import os
import json
import argparse
import sys

def print_color(text, color="green"):
    """Print colored text to the console."""
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "purple": "\033[95m",
        "cyan": "\033[96m",
        "white": "\033[97m",
        "end": "\033[0m"
    }
    
    print(f"{colors.get(color, '')}{text}{colors['end']}")

def validate_email(email):
    """Simple email validation."""
    import re
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(pattern, email) is not None

def save_config(api_key, email, config_file="config.json"):
    """Save API key and email to config file."""
    config = {
        "api_key": api_key,
        "email": email
    }
    
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)
    
    print_color(f"Configuration saved to {config_file}", "green")

def setup_env_vars(api_key, email):
    """Generate commands to set up environment variables."""
    if os.name == "posix":  # Linux/Mac
        print_color("\nTo set environment variables for the current session:", "blue")
        print(f"export NCBI_API_KEY='{api_key}'")
        print(f"export NCBI_EMAIL='{email}'")
        
        print_color("\nTo set environment variables permanently (add to ~/.bashrc or ~/.zshrc):", "blue")
        print(f"echo 'export NCBI_API_KEY=\"{api_key}\"' >> ~/.bashrc")
        print(f"echo 'export NCBI_EMAIL=\"{email}\"' >> ~/.bashrc")
        print("source ~/.bashrc")
    else:  # Windows
        print_color("\nTo set environment variables for the current session:", "blue")
        print(f"set NCBI_API_KEY={api_key}")
        print(f"set NCBI_EMAIL={email}")
        
        print_color("\nTo set environment variables permanently (Windows):", "blue")
        print(f"setx NCBI_API_KEY \"{api_key}\"")
        print(f"setx NCBI_EMAIL \"{email}\"")

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Setup PubMed MCP Server API key and email")
    parser.add_argument("--api-key", type=str, help="NCBI API key")
    parser.add_argument("--email", type=str, help="Email address for NCBI requests")
    parser.add_argument("--config", type=str, default="config.json", help="Path to configuration file")
    parser.add_argument("--env-only", action="store_true", help="Only show environment variable setup commands")
    return parser.parse_args()

def main():
    """Main function."""
    args = parse_arguments()
    
    # Logo
    print_color("""
    ╔═══════════════════════════════════════════╗
    ║  PubMed MCP API Key Setup                 ║
    ╚═══════════════════════════════════════════╝
    """, "cyan")
    
    # Initial instructions
    print_color("This script helps you set up your NCBI API key and email for the PubMed MCP Server.", "white")
    print_color("An API key allows you to make more requests and get more results per query.", "white")
    print_color("Learn more: https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/", "white")
    print("\n")
    
    # Get API key and email
    api_key = args.api_key
    email = args.email
    
    if not api_key:
        print_color("Please enter your NCBI API key", "yellow")
        print_color("(If you don't have one, get it at https://www.ncbi.nlm.nih.gov/account/)", "yellow")
        api_key = input("API Key: ").strip()
    
    if not email:
        print_color("Please enter your email address", "yellow")
        print_color("(NCBI recommends providing an email in case they need to contact you)", "yellow")
        email = input("Email: ").strip()
        
        while not validate_email(email) and email:
            print_color("Invalid email format. Please try again.", "red")
            email = input("Email: ").strip()
    
    if not api_key:
        print_color("Warning: No API key provided. You will have reduced query limits.", "yellow")
    
    if not email:
        print_color("Warning: No email provided. NCBI recommends including an email address.", "yellow")
    
    # Save to config file
    if not args.env_only and (api_key or email):
        try:
            save_config(api_key, email, args.config)
        except Exception as e:
            print_color(f"Error saving configuration: {str(e)}", "red")
    
    # Show environment variable setup
    if api_key or email:
        setup_env_vars(api_key, email)
    
    # Final instructions
    print_color("\nYou can now run the PubMed MCP Server with your API key and email:", "green")
    print_color("1. Using the config file:", "blue")
    print(f"   python python-pubmed-mcp-enhanced.py --config {args.config}")
    print_color("2. Using command line arguments:", "blue")
    print(f"   python python-pubmed-mcp-enhanced.py --api-key {api_key} --email {email}")
    print_color("3. Using environment variables (after setting them up as shown above)", "blue")
    print("   python python-pubmed-mcp-enhanced.py")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_color("\nSetup cancelled by user.", "yellow")
        sys.exit(1)
