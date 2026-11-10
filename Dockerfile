FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY kpc kpc
COPY static static
COPY personas/public personas/public
COPY config.public.json .
ENV KPC_CONFIG=/app/config.public.json
EXPOSE 8917
CMD ["python", "-m", "kpc.server"]
