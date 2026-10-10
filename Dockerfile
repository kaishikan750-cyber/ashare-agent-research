FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CN_OUTPUT_ROOT=/app/outputs/stage3
WORKDIR /app
COPY requirements-stage3-lock.txt ./
RUN pip install --no-cache-dir -r requirements-stage3-lock.txt && pip check
COPY cn_research ./cn_research
COPY research_agent ./research_agent
COPY api ./api
COPY frontend ./frontend
COPY mcp_server ./mcp_server
COPY configs ./configs
COPY .agents ./.agents
COPY data/sample_ashare.csv data/sample_stage3.csv ./data/
RUN useradd --create-home research && mkdir -p /app/outputs && chown -R research:research /app
USER research
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
