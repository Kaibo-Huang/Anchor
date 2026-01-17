"""
Tests for TwelveLabs service - video understanding, search, and embeddings.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Ensure backend is in path for imports
backend_path = Path(__file__).parent.parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))


@pytest.fixture(autouse=True)
def clear_twelvelabs_cache():
    """Clear the lru_cache before each test."""
    try:
        from services.twelvelabs_service import get_twelvelabs_client
        get_twelvelabs_client.cache_clear()
    except Exception:
        pass
    yield
    try:
        from services.twelvelabs_service import get_twelvelabs_client
        get_twelvelabs_client.cache_clear()
    except Exception:
        pass


class TestGetTwelvelabsClient:
    """Test TwelveLabs client initialization."""

    def test_get_client_returns_twelvelabs_instance(self):
        """Test that client returns a TwelveLabs instance with correct API key."""
        with patch("services.twelvelabs_service.TwelveLabs") as mock_client_class, \
             patch("services.twelvelabs_service.get_settings") as mock_settings:

            mock_settings.return_value.twelvelabs_api_key = "test-api-key"
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance

            from services.twelvelabs_service import get_twelvelabs_client
            get_twelvelabs_client.cache_clear()

            client = get_twelvelabs_client()

            # Verify client was created with correct API key
            mock_client_class.assert_called_with(api_key="test-api-key")
            assert client == mock_instance

    def test_get_client_caching(self):
        """Test that lru_cache works for singleton pattern."""
        with patch("services.twelvelabs_service.TwelveLabs") as mock_client_class, \
             patch("services.twelvelabs_service.get_settings") as mock_settings:

            mock_settings.return_value.twelvelabs_api_key = "test-api-key"
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance

            from services.twelvelabs_service import get_twelvelabs_client
            get_twelvelabs_client.cache_clear()

            # Call twice
            client1 = get_twelvelabs_client()
            client2 = get_twelvelabs_client()

            # Should be same instance
            assert client1 is client2
            # Should only construct once (cached)
            assert mock_client_class.call_count == 1


class TestCreateIndex:
    """Test index creation."""

    def test_create_index_success(self):
        """Test successful index creation."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            mock_index = MagicMock()
            mock_index.id = "test-index-id"
            mock_client.indexes.create.return_value = mock_index

            from services.twelvelabs_service import create_index
            result = create_index("event_123")

            assert result == "test-index-id"
            mock_client.indexes.create.assert_called_once()

            # Verify correct models are used
            call_kwargs = mock_client.indexes.create.call_args[1]
            assert call_kwargs["index_name"] == "event_123"
            assert len(call_kwargs["models"]) == 2

    def test_create_index_with_models(self):
        """Test that correct models are configured."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            mock_index = MagicMock()
            mock_index.id = "test-index-id"
            mock_client.indexes.create.return_value = mock_index

            from services.twelvelabs_service import create_index
            create_index("event_456")

            # Verify marengo and pegasus models are used
            call_kwargs = mock_client.indexes.create.call_args[1]
            model_names = [m.model_name for m in call_kwargs["models"]]
            assert "marengo2.7" in model_names
            assert "pegasus1.2" in model_names


class TestIndexVideo:
    """Test video indexing."""

    def test_index_video_success(self):
        """Test successful video indexing."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            mock_task = MagicMock()
            mock_task.id = "task-123"
            mock_task.status = "ready"
            mock_client.tasks.create.return_value = mock_task

            from services.twelvelabs_service import index_video
            result = index_video("index-id", "https://s3.example.com/video.mp4")

            assert result == mock_task
            mock_client.tasks.create.assert_called_once_with(
                index_id="index-id",
                video_url="https://s3.example.com/video.mp4",
            )
            mock_task.wait_for_done.assert_called_once_with(sleep_interval=5)

    def test_index_video_no_wait(self):
        """Test video indexing without waiting."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            mock_task = MagicMock()
            mock_client.tasks.create.return_value = mock_task

            from services.twelvelabs_service import index_video
            result = index_video("index-id", "https://s3.example.com/video.mp4", wait=False)

            mock_task.wait_for_done.assert_not_called()


class TestSearchVideos:
    """Test video search functionality."""

    def test_search_videos_success(self):
        """Test successful video search."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            mock_clip1 = MagicMock()
            mock_clip1.video_id = "video-1"
            mock_clip1.start = 10.0
            mock_clip1.end = 15.0
            mock_clip1.confidence = 0.95

            mock_clip2 = MagicMock()
            mock_clip2.video_id = "video-2"
            mock_clip2.start = 30.0
            mock_clip2.end = 35.0
            mock_clip2.confidence = 0.85

            mock_results = MagicMock()
            mock_results.data = [mock_clip1, mock_clip2]
            mock_client.search.query.return_value = mock_results

            from services.twelvelabs_service import search_videos
            results = search_videos("index-123", "player scoring a goal")

            assert len(results) == 2
            assert results[0]["video_id"] == "video-1"
            assert results[0]["start"] == 10.0
            assert results[0]["end"] == 15.0
            assert results[0]["confidence"] == 0.95

            assert results[1]["video_id"] == "video-2"
            assert results[1]["confidence"] == 0.85

    def test_search_videos_with_options(self):
        """Test search with custom options."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            mock_results = MagicMock()
            mock_results.data = []
            mock_client.search.query.return_value = mock_results

            from services.twelvelabs_service import search_videos
            search_videos("index-123", "test query", search_options=["visual"], limit=5)

            mock_client.search.query.assert_called_once_with(
                index_id="index-123",
                query_text="test query",
                options=["visual"],
                page_limit=5,
            )

    def test_search_videos_default_options(self):
        """Test search uses default visual+audio options."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            mock_results = MagicMock()
            mock_results.data = []
            mock_client.search.query.return_value = mock_results

            from services.twelvelabs_service import search_videos
            search_videos("index-123", "test query")

            call_kwargs = mock_client.search.query.call_args[1]
            assert call_kwargs["options"] == ["visual", "audio"]
            assert call_kwargs["page_limit"] == 20  # default limit

    def test_search_videos_empty_results(self):
        """Test search with no results."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            mock_results = MagicMock()
            mock_results.data = []
            mock_client.search.query.return_value = mock_results

            from services.twelvelabs_service import search_videos
            results = search_videos("index-123", "nonexistent query")

            assert results == []


class TestCreateVideoEmbeddings:
    """Test video embedding creation."""

    def test_create_video_embeddings_success(self):
        """Test successful video embedding creation."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            # Create mock segment embeddings
            mock_segment1 = MagicMock()
            mock_segment1.start_offset_sec = 0.0
            mock_segment1.end_offset_sec = 5.0
            mock_segment1.embedding = [0.1, 0.2, 0.3] * 341 + [0.4]  # 1024 dim

            mock_segment2 = MagicMock()
            mock_segment2.start_offset_sec = 5.0
            mock_segment2.end_offset_sec = 10.0
            mock_segment2.embedding = [0.5, 0.6, 0.7] * 341 + [0.8]

            mock_task = MagicMock()
            mock_task.video_embeddings = [mock_segment1, mock_segment2]
            mock_client.embed.task.create.return_value = mock_task

            from services.twelvelabs_service import create_video_embeddings
            result = create_video_embeddings("https://s3.example.com/video.mp4")

            assert len(result) == 2
            assert result[0]["start_time"] == 0.0
            assert result[0]["end_time"] == 5.0
            assert len(result[0]["embedding"]) == 1024

            mock_client.embed.task.create.assert_called_once_with(
                model_name="Marengo-retrieval-2.7",
                video_url="https://s3.example.com/video.mp4",
            )
            mock_task.wait_for_done.assert_called_once()

    def test_create_video_embeddings_empty(self):
        """Test video embeddings when no segments returned."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            mock_task = MagicMock()
            mock_task.video_embeddings = None
            mock_client.embed.task.create.return_value = mock_task

            from services.twelvelabs_service import create_video_embeddings
            result = create_video_embeddings("https://s3.example.com/video.mp4")

            assert result == []


class TestCreateTextEmbedding:
    """Test text embedding creation."""

    def test_create_text_embedding_success(self):
        """Test successful text embedding creation."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            mock_result = MagicMock()
            mock_result.embedding = [0.1, 0.2, 0.3] * 341 + [0.4]  # 1024 dim
            mock_client.embed.create.return_value = mock_result

            from services.twelvelabs_service import create_text_embedding
            result = create_text_embedding("fast movement, intense action")

            assert len(result) == 1024
            mock_client.embed.create.assert_called_once_with(
                model_name="Marengo-retrieval-2.7",
                text="fast movement, intense action",
            )

    def test_create_text_embedding_empty(self):
        """Test text embedding when no result."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            mock_result = MagicMock(spec=[])  # No embedding attribute
            mock_client.embed.create.return_value = mock_result

            from services.twelvelabs_service import create_text_embedding
            result = create_text_embedding("test text")

            assert result == []


class TestGetVibeEmbedding:
    """Test vibe anchor embedding retrieval."""

    def test_get_vibe_embedding_high_energy(self):
        """Test high_energy vibe embedding."""
        with patch("services.twelvelabs_service.create_text_embedding") as mock_create_embedding:
            mock_create_embedding.return_value = [0.1] * 1024

            from services.twelvelabs_service import get_vibe_embedding
            result = get_vibe_embedding("high_energy")

            assert len(result) == 1024
            # Should use correct description
            call_text = mock_create_embedding.call_args[0][0]
            assert "intense action" in call_text or "excitement" in call_text

    def test_get_vibe_embedding_emotional(self):
        """Test emotional vibe embedding."""
        with patch("services.twelvelabs_service.create_text_embedding") as mock_create_embedding:
            mock_create_embedding.return_value = [0.2] * 1024

            from services.twelvelabs_service import get_vibe_embedding
            result = get_vibe_embedding("emotional")

            assert len(result) == 1024
            call_text = mock_create_embedding.call_args[0][0]
            assert "emotional" in call_text or "heartfelt" in call_text

    def test_get_vibe_embedding_calm(self):
        """Test calm vibe embedding."""
        with patch("services.twelvelabs_service.create_text_embedding") as mock_create_embedding:
            mock_create_embedding.return_value = [0.3] * 1024

            from services.twelvelabs_service import get_vibe_embedding
            result = get_vibe_embedding("calm")

            assert len(result) == 1024
            call_text = mock_create_embedding.call_args[0][0]
            assert "peaceful" in call_text or "calm" in call_text or "relaxed" in call_text

    def test_get_vibe_embedding_invalid(self):
        """Test invalid vibe raises error."""
        from services.twelvelabs_service import get_vibe_embedding

        with pytest.raises(ValueError) as exc_info:
            get_vibe_embedding("invalid_vibe")

        assert "Unknown vibe" in str(exc_info.value)


class TestGetVideoAnalysis:
    """Test video analysis retrieval."""

    def test_get_video_analysis_success(self):
        """Test successful video analysis retrieval."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            mock_video = MagicMock()
            mock_video.id = "video-123"
            mock_video.status = "ready"
            mock_video.metadata.duration = 120.5
            mock_video.metadata.filename = "test_video.mp4"
            mock_client.indexes.videos.retrieve.return_value = mock_video

            from services.twelvelabs_service import get_video_analysis
            result = get_video_analysis("index-123", "video-123")

            assert result["video_id"] == "video-123"
            assert result["duration"] == 120.5
            assert result["filename"] == "test_video.mp4"
            assert result["status"] == "ready"

            mock_client.indexes.videos.retrieve.assert_called_once_with(
                index_id="index-123",
                video_id="video-123",
            )

    def test_get_video_analysis_missing_metadata(self):
        """Test video analysis with missing metadata fields."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            mock_video = MagicMock(spec=["id", "status", "metadata"])
            mock_video.id = "video-123"
            mock_video.status = "ready"
            mock_video.metadata = MagicMock(spec=[])  # No duration/filename
            mock_client.indexes.videos.retrieve.return_value = mock_video

            from services.twelvelabs_service import get_video_analysis
            result = get_video_analysis("index-123", "video-123")

            assert result["video_id"] == "video-123"
            assert result["duration"] == 0
            assert result["filename"] == ""


class TestDeleteIndex:
    """Test index deletion."""

    def test_delete_index_success(self):
        """Test successful index deletion."""
        with patch("services.twelvelabs_service.get_twelvelabs_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            from services.twelvelabs_service import delete_index
            delete_index("index-123")

            mock_client.indexes.delete.assert_called_once_with(index_id="index-123")


class TestVibeDescriptions:
    """Test vibe description constants."""

    def test_vibe_descriptions_exist(self):
        """Test that all vibe descriptions are defined."""
        from services.twelvelabs_service import VIBE_DESCRIPTIONS

        assert "high_energy" in VIBE_DESCRIPTIONS
        assert "emotional" in VIBE_DESCRIPTIONS
        assert "calm" in VIBE_DESCRIPTIONS

    def test_vibe_descriptions_not_empty(self):
        """Test that vibe descriptions have content."""
        from services.twelvelabs_service import VIBE_DESCRIPTIONS

        for vibe, description in VIBE_DESCRIPTIONS.items():
            assert len(description) > 10, f"{vibe} description too short"


class TestEmbeddingSimilarity:
    """Test embedding similarity calculations (used in vibe matching)."""

    def test_cosine_similarity_basic(self):
        """Test basic cosine similarity calculation."""
        from scipy.spatial.distance import cosine

        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]

        similarity = 1 - cosine(vec1, vec2)
        assert similarity == pytest.approx(1.0, rel=1e-6)

    def test_cosine_similarity_orthogonal(self):
        """Test orthogonal vectors have zero similarity."""
        from scipy.spatial.distance import cosine

        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]

        similarity = 1 - cosine(vec1, vec2)
        assert similarity == pytest.approx(0.0, rel=1e-6)

    def test_cosine_similarity_opposite(self):
        """Test opposite vectors have -1 similarity."""
        from scipy.spatial.distance import cosine

        vec1 = [1.0, 0.0, 0.0]
        vec2 = [-1.0, 0.0, 0.0]

        similarity = 1 - cosine(vec1, vec2)
        assert similarity == pytest.approx(-1.0, rel=1e-6)

    def test_vibe_matching_workflow(self):
        """Test the full vibe matching workflow with mock embeddings."""
        from scipy.spatial.distance import cosine

        # Simulate video segment embeddings
        segment_embeddings = [
            {"start": 0, "end": 5, "embedding": [0.8, 0.5, 0.1]},  # High energy-like
            {"start": 5, "end": 10, "embedding": [0.1, 0.8, 0.2]},  # Emotional-like
            {"start": 10, "end": 15, "embedding": [0.2, 0.1, 0.9]},  # Calm-like
        ]

        # Simulate vibe anchors
        vibe_anchors = {
            "high_energy": [0.9, 0.4, 0.0],
            "emotional": [0.0, 0.9, 0.1],
            "calm": [0.1, 0.0, 0.95],
        }

        # Find best segment for "high_energy"
        target_vibe = "high_energy"
        vibe_vector = vibe_anchors[target_vibe]

        scores = []
        for seg in segment_embeddings:
            similarity = 1 - cosine(seg["embedding"], vibe_vector)
            scores.append((seg, similarity))

        # Sort by similarity
        scores.sort(key=lambda x: x[1], reverse=True)

        # First segment should be best match for high_energy
        assert scores[0][0]["start"] == 0
        assert scores[0][1] > 0.9  # High similarity
