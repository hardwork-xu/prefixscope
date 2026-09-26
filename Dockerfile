FROM python:3.12.10-slim-bookworm
WORKDIR /app
COPY requirements.lock requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
RUN python -m pip install --no-cache-dir --no-build-isolation .
COPY examples/ examples/
USER 65534:65534
ENTRYPOINT ["python", "-m", "prefixscope"]
CMD ["demo"]
