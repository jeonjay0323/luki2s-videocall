import os
import subprocess

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.transcriptions.language import Language
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.stt import GoogleSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.simli.video import SimliVideoService
from pipecat.transports.base_transport import BaseTransport, TransportParams

try:
    from pipecat.transports.daily.transport import DailyParams
except ImportError:
    DailyParams = None  # Daily SDK 미설치 시 webrtc만 사용

load_dotenv(override=True)

# --- Google Cloud / Vertex (Gemini) 설정 ---
GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
GCP_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")


def vertex_token() -> str:
    """gcloud로 Vertex 액세스 토큰 발급 (약 1시간 유효)."""
    return subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode().strip()


transport_params = {
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_out_enabled=True,
        video_out_is_live=True,
        video_out_width=512,
        video_out_height=512,
        vad_analyzer=SileroVADAnalyzer(),
    ),
}

# Daily SDK가 설치돼 있으면 daily 트랜스포트도 등록
if DailyParams is not None:
    transport_params["daily"] = lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_out_enabled=True,
        video_out_is_live=True,
        video_out_width=512,
        video_out_height=512,
        vad_analyzer=SileroVADAnalyzer(),
    )


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting bot (Google STT + Vertex Gemini + ElevenLabs + Simli)")

    # STT: Google Cloud Speech-to-Text (한국어), ADC(gcloud) 자동 사용
    stt = GoogleSTTService(
        settings=GoogleSTTService.Settings(languages=[Language.KO_KR], model="latest_long"),
    )

    # LLM: Vertex AI Gemini (OpenAI 호환 엔드포인트)
    vertex_base = (
        f"https://{GCP_LOCATION}-aiplatform.googleapis.com/v1/projects/"
        f"{GCP_PROJECT}/locations/{GCP_LOCATION}/endpoints/openapi"
    )
    llm = OpenAILLMService(
        model="google/gemini-2.5-flash",
        api_key=vertex_token(),
        base_url=vertex_base,
    )

    # TTS: ElevenLabs (지정 voice)
    tts = ElevenLabsTTSService(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
        model="eleven_turbo_v2_5",
    )

    # 얼굴: Simli (legacy face → is_trinity_avatar=False)
    simli_ai = SimliVideoService(
        api_key=os.getenv("SIMLI_API_KEY"),
        face_id=os.getenv("SIMLI_FACE_ID"),
        is_trinity_avatar=False,
        max_session_length=1800,
        max_idle_time=600,
    )

    messages = [
        {
            "role": "system",
            "content": (
                "너는 사용자의 친한 친구야. 무조건 한국어로만, 반말로, 짧고 자연스럽게 대화해. "
                "영어 쓰지 마. 대화가 시작되면 먼저 가볍게 인사해."
            ),
        },
    ]

    context = LLMContext(messages)
    context_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            simli_ai,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        # 접속하면 고정 대사로 먼저 인사 (LLM 안 거치고 TTS 직접 → 빈 입력 400 회피)
        await task.queue_frames([TTSSpeakFrame("어 뭐야! 누구세요?")])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from fastapi.staticfiles import StaticFiles
    from pipecat.runner.run import app, main

    # LUKI2DS 영상통화 페이지(call.html 디자인)를 봇과 같은 origin에 서빙 → /luki/
    _web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    app.mount("/luki", StaticFiles(directory=_web_dir, html=True), name="luki")

    main()
