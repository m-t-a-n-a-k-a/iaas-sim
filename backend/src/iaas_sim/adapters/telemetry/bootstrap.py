from __future__ import annotations

import logging
import os
from typing import Final

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_telemetry() -> None:
    service_name = os.getenv("OTEL_SERVICE_NAME", "iaas-sim")
    resource = Resource.create({"service.name": service_name})

    trace_provider = TracerProvider(resource=resource)
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-lgtm:4317")
    span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    trace_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(trace_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
        export_interval_millis=5000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    LoggingInstrumentor().instrument(set_logging_format=True)

    logger: Final[logging.Logger] = logging.getLogger("iaas_sim")
    logger.setLevel(logging.INFO)
    logger.info("telemetry configured", extra={"component": "bootstrap"})

    meter = metrics.get_meter("iaas_sim.bootstrap")
    startup_counter = meter.create_counter("iaas_sim_startup_total", description="Startup counter")
    startup_counter.add(1, {"component": "bootstrap"})


def instrument_fastapi_app(app: FastAPI) -> None:
    FastAPIInstrumentor.instrument_app(app)
