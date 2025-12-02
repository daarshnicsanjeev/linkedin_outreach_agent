@echo off
cd /d "C:\Users\daars\.gemini\antigravity\scratch\linkedin_outreach_agent"
echo Starting LinkedIn Agent at %DATE% %TIME% >> agent_scheduler_log.txt
python linkedin_agent.py >> agent_scheduler_log.txt 2>&1
echo Finished at %DATE% %TIME% >> agent_scheduler_log.txt
echo ---------------------------------------- >> agent_scheduler_log.txt
