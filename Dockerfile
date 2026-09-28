# Builder
# ----------------------------------------
FROM python:3.12.11-slim AS builder

ENV UV_UNSAFE_NO_IO_URING=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml ./pyproject.toml

# uv.lock이 아직 없다(레포 최초 상태) — 있으면 그대로 쓰고 없으면 새로 만든다.
# lock이 생성되면 커밋해두고, 이후에는 metering-api/metering-worker처럼
# `COPY pyproject.toml uv.lock ./` + `uv sync --frozen`으로 바꾸는 것을 권장한다.
RUN uv sync --no-dev

# Image
# ---------------------------------------
FROM python:3.12.11-slim

WORKDIR /ism-adapter

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY . .
COPY --from=builder /.venv /ism-adapter/.venv
COPY --from=builder /uv.lock /ism-adapter/uv.lock

ENV PATH="/ism-adapter/.venv/bin:$PATH" \
    TZ=UTC

# uv 바이너리를 최종 이미지에도 남겨둔다 — uv.lock이 아직 레포에 커밋되지
# 않은 동안은, 볼륨 마운트(docker-compose-dev.yaml)가 이미지 빌드 시 만든
# uv.lock을 호스트 상태(없음)로 덮어쓰므로 컨테이너 안에서 `uv sync`를 다시
# 실행해 lock을 생성해야 한다. lock을 커밋한 뒤에는 없어도 무방하다.

# 상시 서버가 아니라 CLI 배치다. 2026-09-17 서브커맨드(accounts/resources) 도입
# 이후 CMD는 의도적으로 비워둔다 — account push(기간 없음, 항상 전체 대상)와
# resource/metering push(기간 지정)는 legacy 실행 순서(account→contract→
# resource→metering)상 서로 다른 시점/스케줄로 호출될 수 있어, 이미지 하나를
# 여러 k8s CronJob이 command/args만 다르게 지정해 공유하는 편이 낫다(예:
# `command: ["python", "-m", "ism_adapter.cli", "accounts"]` /
# `[..., "resources", "--resource-type=network,router"]`). 로컬 개발에서는
# docker-compose-dev.yaml이 entrypoint를 tail -f로 덮어써 컨테이너만 띄워두고,
# docker exec로 원하는 서브커맨드를 수동 실행하는 방식을 쓴다.
