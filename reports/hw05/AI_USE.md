# AI Use Statement

## 1. How I Used AI

I used an AI assistant to help organize the homework requirements, review code structure, explain unfamiliar concepts, and suggest debugging steps. I integrated and adjusted the code in my repository, ran the services and experiments, tested the API and UI, collected the screenshots, and checked the final results myself.

## 2. Output That Required Verification

One early suggestion used a newer MCP package version that conflicted with the FastAPI and Starlette versions already used by the project.

## 3. How I Verified It

I checked the installed package versions, ran `pip check`, tested the FastMCP import, and ran the existing FastAPI application again. These checks showed which dependency versions were compatible.

## 4. What I Changed

I used a compatible MCP version and kept the existing FastAPI, Starlette, and Uvicorn versions. After the change, `pip check` reported no broken requirements, FastAPI continued to run, and both MCP servers passed their tool tests.