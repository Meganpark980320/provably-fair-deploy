FROM ghcr.io/foundry-rs/foundry:latest AS foundry
FROM python:3.12-slim
COPY --from=foundry /usr/local/bin/anvil /usr/local/bin/anvil
WORKDIR /app
RUN pip install --no-cache-dir flask web3 requests
COPY out/ProvablyFair.sol/ProvablyFair.json /app/out/ProvablyFair.sol/ProvablyFair.json
COPY service/serve.py /app/service/serve.py
ENV ANVIL_PORT=8545
EXPOSE 8000
CMD ["python", "service/serve.py"]
