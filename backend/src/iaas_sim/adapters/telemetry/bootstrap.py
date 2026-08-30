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

logger: Final[logging.Logger] = logging.getLogger("iaas_sim.telemetry")


def configure_telemetry() -> None:
    service_name = os.getenv("OTEL_SERVICE_NAME", "iaas-sim")
    resource = Resource.create({"service.name": service_name})
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-lgtm:4317")

    current_trace_provider = trace.get_tracer_provider()
    if not isinstance(current_trace_provider, TracerProvider):
        trace_provider = TracerProvider(resource=resource)
        span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        trace_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(trace_provider)

    current_meter_provider = metrics.get_meter_provider()
    if not isinstance(current_meter_provider, MeterProvider):
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
            export_interval_millis=5000,
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)

    LoggingInstrumentor().instrument(set_logging_format=True)

    logger.setLevel(logging.INFO)
    logger.info("telemetry configured", extra={"component": "bootstrap"})

    meter = metrics.get_meter("iaas_sim.bootstrap")
    startup_counter = meter.create_counter(
        "iaas_sim_startup_total",
        description="Application startup count",
    )
    startup_counter.add(1, {"component": "bootstrap"})

    tracer = trace.get_tracer("iaas_sim.bootstrap")
    with tracer.start_as_current_span("iaas_sim.startup") as span:
        span.set_attribute("component", "bootstrap")
        logger.info("telemetry span initialized", extra={"component": "bootstrap"})


def instrument_fastapi_app(app: FastAPI) -> None:
    FastAPIInstrumentor.instrument_app(app)


def configure_app_telemetry(app: FastAPI) -> None:
    configure_telemetry()
    instrument_fastapi_app(app)
    app.state.telemetry_ready = True
