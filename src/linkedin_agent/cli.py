"""
LinkedIn Agent CLI
==================
Unified command-line interface for all LinkedIn agents.

Usage:
    python -m linkedin_agent <command> [options]
    
Commands:
    outreach      - Run the connection outreach agent
    comment       - Run the comment generation agent  
    engagement    - Run the engagement monitoring agent
    notification  - Run the notification processing agent
    search        - Run the search/prospect agent
    withdraw      - Run the invite withdrawal agent
"""

import argparse
import asyncio
import sys


def main():
    parser = argparse.ArgumentParser(
        description="LinkedIn Automation Agent Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m linkedin_agent comment
    python -m linkedin_agent engagement --headless
    python -m linkedin_agent outreach --config custom_config.json
        """
    )
    
    parser.add_argument(
        "command",
        choices=["outreach", "comment", "engagement", "notification", "search", "withdraw"],
        help="Which agent to run"
    )
    
    parser.add_argument(
        "--config", "-c",
        default="config.json",
        help="Path to configuration file (default: config.json)"
    )
    
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true", 
        help="Enable debug mode with extra logging"
    )
    
    args = parser.parse_args()
    
    # Import and run the appropriate agent
    try:
        if args.command == "outreach":
            from .agents.outreach_agent import OutreachAgent
            agent = OutreachAgent(config_path=args.config)
            
        elif args.command == "comment":
            from .agents.comment_agent import CommentAgent
            agent = CommentAgent(config_path=args.config)
            
        elif args.command == "engagement":
            from .agents.engagement_agent import EngagementAgent
            agent = EngagementAgent(config_path=args.config)
            
        elif args.command == "notification":
            from .agents.notification_agent import NotificationAgent
            agent = NotificationAgent(config_path=args.config)
            
        elif args.command == "search":
            from .agents.search_agent import SearchAgent
            agent = SearchAgent(config_path=args.config)
            
        elif args.command == "withdraw":
            from .agents.invite_withdrawal_agent import InviteWithdrawalAgent
            agent = InviteWithdrawalAgent(config_path=args.config)
        
        # Run the agent
        asyncio.run(agent.execute())
        
    except ImportError as e:
        print(f"Error: Agent module not found: {e}")
        print("Note: Agent refactoring may still be in progress.")
        print("You can still run agents directly from the project root:")
        print(f"    python {args.command}_agent.py")
        sys.exit(1)
        
    except KeyboardInterrupt:
        print("\nAgent interrupted by user")
        sys.exit(0)
        
    except Exception as e:
        print(f"Agent error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
