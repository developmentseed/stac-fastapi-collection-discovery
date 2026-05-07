import base64
import copy

import pytest
import respx
from httpx import Response


class TestCollectionSearchClient:
    """Test cases for CollectionSearchClient."""

    def test_encode_decode_token(self, collection_search_client):
        """Test token encoding and decoding."""
        test_state = {
            "current": {"api1": "https://api1.example.com/collections"},
            "next": {"api1": "https://api1.example.com/collections?token=next"},
            "is_first_page": False,
        }

        token = collection_search_client._encode_token(test_state)
        decoded_state = collection_search_client._decode_token(token)

        assert decoded_state == test_state
        assert isinstance(token, str)

        # Verify token is valid base64
        base64.urlsafe_b64decode(token.encode())

    def test_encode_token_consistency(self, collection_search_client):
        """Test that encoding the same state produces the same token."""
        test_state = {"current": {"api1": "url1"}, "is_first_page": True}

        token1 = collection_search_client._encode_token(test_state)
        token2 = collection_search_client._encode_token(test_state)

        assert token1 == token2

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_first_page(
        self, collection_search_client, mock_request, sample_collections_response
    ):
        """Test collection search on first page with multiple APIs."""
        # Mock responses from two APIs - need deep copy to avoid shared references
        api1_response = copy.deepcopy(sample_collections_response)
        api1_response["collections"][0]["id"] = "api1-collection-1"
        api1_response["collections"][1]["id"] = "api1-collection-2"

        api2_response = copy.deepcopy(sample_collections_response)
        api2_response["collections"][0]["id"] = "api2-collection-1"
        api2_response["collections"][1]["id"] = "api2-collection-2"

        respx.get("https://api1.example.com/collections").mock(
            return_value=Response(200, json=api1_response)
        )
        respx.get("https://api2.example.com/collections").mock(
            return_value=Response(200, json=api2_response)
        )

        result = await collection_search_client.all_collections(request=mock_request)

        # Should have collections from both APIs
        assert len(result.collections["collections"]) == 4
        assert result.collections["numberReturned"] == 4

        # Check collection IDs
        collection_ids = [c["id"] for c in result.collections["collections"]]
        assert "api1-collection-1" in collection_ids
        assert "api1-collection-2" in collection_ids
        assert "api2-collection-1" in collection_ids
        assert "api2-collection-2" in collection_ids

        # Check links
        self_link = next(
            link for link in result.collections["links"] if link["rel"] == "self"
        )
        assert self_link["href"] == str(mock_request.url)

        # Should have canonical links to both APIs
        canonical_links = [
            link for link in result.collections["links"] if link["rel"] == "canonical"
        ]
        assert len(canonical_links) == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_with_pagination(
        self, collection_search_client, mock_request, sample_collections_response
    ):
        """Test collection search with pagination."""
        # Mock response with next link
        api_response = sample_collections_response.copy()
        api_response["links"] = [
            {"rel": "self", "href": "https://api1.example.com/collections"},
            {
                "rel": "next",
                "href": "https://api1.example.com/collections?token=next_page",
            },
        ]

        respx.get("https://api1.example.com/collections").mock(
            return_value=Response(200, json=api_response)
        )
        respx.get("https://api2.example.com/collections").mock(
            return_value=Response(200, json=sample_collections_response)
        )

        result = await collection_search_client.all_collections(request=mock_request)

        # Should have next link
        next_link = next(
            (link for link in result.collections["links"] if link["rel"] == "next"), None
        )
        assert next_link is not None
        assert "token=" in next_link["href"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_with_token(
        self, collection_search_client, mock_request, sample_collections_response
    ):
        """Test collection search with pagination token."""
        # Create a pagination token
        token_state = {
            "current": {
                "https://api1.example.com": "https://api1.example.com/collections?page=2",
                "https://api2.example.com": "https://api2.example.com/collections?page=2",
            },
            "is_first_page": False,
        }
        token = collection_search_client._encode_token(token_state)

        # Mock responses for page 2
        respx.get("https://api1.example.com/collections?page=2").mock(
            return_value=Response(200, json=sample_collections_response)
        )
        respx.get("https://api2.example.com/collections?page=2").mock(
            return_value=Response(200, json=sample_collections_response)
        )

        result = await collection_search_client.all_collections(
            request=mock_request, token=token
        )

        assert len(result.collections["collections"]) == 4
        assert result.collections["numberReturned"] == 4

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_with_parameters(
        self, collection_search_client, mock_request, sample_collections_response
    ):
        """Test collection search with query parameters."""
        respx.get(
            "https://api1.example.com/collections?bbox=-180,-90,180,90&datetime=2020-01-01T00:00:00Z/2021-01-01T00:00:00Z&limit=10"
        ).mock(return_value=Response(200, json=sample_collections_response))
        respx.get(
            "https://api2.example.com/collections?bbox=-180,-90,180,90&datetime=2020-01-01T00:00:00Z/2021-01-01T00:00:00Z&limit=10"
        ).mock(return_value=Response(200, json=sample_collections_response))

        result = await collection_search_client.all_collections(
            request=mock_request,
            bbox=[-180, -90, 180, 90],
            datetime="2020-01-01T00:00:00Z/2021-01-01T00:00:00Z",
            limit=10,
        )

        assert len(result.collections["collections"]) == 4
        assert result.collections["numberReturned"] == 4

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_api_error_strict_false(
        self, collection_search_client, mock_request, sample_collections_response
    ):
        """Test that one failing API doesn't crash when strict=False (default)."""
        # One API returns error, one succeeds
        respx.get("https://api1.example.com/collections").mock(
            return_value=Response(500, json={"error": "Internal server error"})
        )
        respx.get("https://api2.example.com/collections").mock(
            return_value=Response(200, json=sample_collections_response)
        )

        result = await collection_search_client.all_collections(request=mock_request)

        # Should only have collections from api2
        assert len(result.collections["collections"]) == 2
        assert result.collections["numberReturned"] == 2
        assert result.failed_apis == ["https://api1.example.com"]

        # Verify state only contains api2
        for link in result.collections["links"]:
            if link["rel"] in ("next", "previous"):
                decoded = collection_search_client._decode_token(
                    link["href"].split("token=")[1]
                )
                assert "https://api1.example.com" not in decoded["current"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_api_error_strict_true(
        self, collection_search_client, mock_request, sample_collections_response
    ):
        """Test that one failing API raises when strict=True."""
        from httpx import HTTPStatusError

        respx.get("https://api1.example.com/collections").mock(
            return_value=Response(500, json={"error": "Internal server error"})
        )
        respx.get("https://api2.example.com/collections").mock(
            return_value=Response(200, json=sample_collections_response)
        )

        with pytest.raises(HTTPStatusError):
            await collection_search_client.all_collections(
                request=mock_request, strict=True
            )

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_with_apis_parameter(
        self, collection_search_client, mock_request, sample_collections_response
    ):
        """Test collection search with custom APIs parameter."""
        # Mock responses for specific APIs
        api3_response = copy.deepcopy(sample_collections_response)
        api3_response["collections"][0]["id"] = "api3-collection-1"

        api4_response = copy.deepcopy(sample_collections_response)
        api4_response["collections"][0]["id"] = "api4-collection-1"

        respx.get("https://api3.example.com/collections").mock(
            return_value=Response(200, json=api3_response)
        )
        respx.get("https://api4.example.com/collections").mock(
            return_value=Response(200, json=api4_response)
        )

        # Test with custom APIs list
        custom_apis = ["https://api3.example.com", "https://api4.example.com"]
        result = await collection_search_client.all_collections(
            request=mock_request, apis=custom_apis
        )

        # Should only have collections from the specified APIs
        assert len(result.collections["collections"]) == 4  # 2 collections per API
        collection_ids = [c["id"] for c in result.collections["collections"]]
        assert "api3-collection-1" in collection_ids
        assert "api4-collection-1" in collection_ids

        # Should have canonical links to both specified APIs
        canonical_links = [
            link for link in result.collections["links"] if link["rel"] == "canonical"
        ]
        assert len(canonical_links) == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_with_single_api(
        self, collection_search_client, mock_request, sample_collections_response
    ):
        """Test collection search with single API in apis parameter."""
        respx.get("https://single-api.example.com/collections").mock(
            return_value=Response(200, json=sample_collections_response)
        )

        # Test with single API
        result = await collection_search_client.all_collections(
            request=mock_request, apis=["https://single-api.example.com"]
        )

        # Should have collections from only one API
        assert len(result.collections["collections"]) == 2
        assert result.collections["numberReturned"] == 2

        # Should have only one canonical link
        canonical_links = [
            link for link in result.collections["links"] if link["rel"] == "canonical"
        ]
        assert len(canonical_links) == 1

    @pytest.mark.asyncio
    async def test_all_collections_empty_apis_parameter(self, collection_search_client):
        """Test collection search with empty apis parameter raises HTTPException."""
        from unittest.mock import Mock

        from fastapi import HTTPException

        # Create a mock request with empty upstream_api_urls in settings
        mock_request = Mock()
        mock_request.app.state.settings.upstream_api_urls = []

        with pytest.raises(HTTPException) as exc_info:
            await collection_search_client.all_collections(request=mock_request, apis=[])

        assert exc_info.value.status_code == 400
        assert "No APIs specified" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_all_collections_no_apis_fallback_to_settings(
        self, collection_search_client
    ):
        """Test that when no apis parameter provided, it falls back to settings."""
        from unittest.mock import Mock

        from fastapi import HTTPException

        # Create a mock request with empty upstream_api_urls in settings
        mock_request = Mock()
        mock_request.app.state.settings.upstream_api_urls = []

        with pytest.raises(HTTPException) as exc_info:
            await collection_search_client.all_collections(request=mock_request)

        assert exc_info.value.status_code == 400
        assert "No APIs specified" in exc_info.value.detail

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_apis_parameter_with_pagination(
        self, collection_search_client, mock_request, sample_collections_response
    ):
        """Test collection search with apis parameter and pagination."""
        # Mock response with next link for custom API
        api_response = sample_collections_response.copy()
        api_response["links"] = [
            {"rel": "self", "href": "https://custom-api.example.com/collections"},
            {
                "rel": "next",
                "href": "https://custom-api.example.com/collections?token=next_page",
            },
        ]

        respx.get("https://custom-api.example.com/collections").mock(
            return_value=Response(200, json=api_response)
        )

        result = await collection_search_client.all_collections(
            request=mock_request, apis=["https://custom-api.example.com"]
        )

        # Should have next link
        next_link = next(
            (link for link in result.collections["links"] if link["rel"] == "next"), None
        )
        assert next_link is not None
        assert "token=" in next_link["href"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_apis_parameter_with_search_params(
        self, collection_search_client, mock_request, sample_collections_response
    ):
        """Test collection search with apis parameter and search parameters."""
        respx.get(
            "https://search-api.example.com/collections?bbox=-180,-90,180,90&datetime=2020-01-01T00:00:00Z/2021-01-01T00:00:00Z&limit=5"
        ).mock(return_value=Response(200, json=sample_collections_response))

        result = await collection_search_client.all_collections(
            request=mock_request,
            apis=["https://search-api.example.com"],
            bbox=[-180, -90, 180, 90],
            datetime="2020-01-01T00:00:00Z/2021-01-01T00:00:00Z",
            limit=5,
        )

        assert len(result.collections["collections"]) == 2
        assert result.collections["numberReturned"] == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_apis_parameter_preserved_in_pagination(
        self, collection_search_client, mock_request
    ):
        """Test that apis parameter is preserved when following next link."""
        # Mock response with next link for first page
        first_page_response = {
            "collections": [
                {
                    "type": "Collection",
                    "id": "api3-page1-collection-1",
                    "title": "Collection Page 1",
                    "description": "First page collection",
                    "extent": {
                        "spatial": {"bbox": [[-180, -90, 180, 90]]},
                        "temporal": {
                            "interval": [["2020-01-01T00:00:00Z", "2021-01-01T00:00:00Z"]]
                        },
                    },
                    "license": "MIT",
                    "links": [],
                },
            ],
            "links": [
                {"rel": "self", "href": "https://api3.example.com/collections"},
                {
                    "rel": "next",
                    "href": "https://api3.example.com/collections?token=page2",
                },
            ],
        }

        # Mock response for second page
        second_page_response = {
            "collections": [
                {
                    "type": "Collection",
                    "id": "api3-page2-collection-1",
                    "title": "Collection Page 2",
                    "description": "Second page collection",
                    "extent": {
                        "spatial": {"bbox": [[-180, -90, 180, 90]]},
                        "temporal": {
                            "interval": [["2020-01-01T00:00:00Z", "2021-01-01T00:00:00Z"]]
                        },
                    },
                    "license": "MIT",
                    "links": [],
                },
            ],
            "links": [
                {
                    "rel": "self",
                    "href": "https://api3.example.com/collections?token=page2",
                },
                {
                    "rel": "previous",
                    "href": "https://api3.example.com/collections",
                },
            ],
        }

        respx.route(url="https://api3.example.com/collections?token=page2").mock(
            return_value=Response(200, json=second_page_response)
        )
        respx.route(url="https://api3.example.com/collections").mock(
            return_value=Response(200, json=first_page_response)
        )

        # First request with custom apis parameter
        custom_apis = ["https://api3.example.com"]
        first_result = await collection_search_client.all_collections(
            request=mock_request, apis=custom_apis
        )

        # Extract the next link and token from first page
        next_link = next(
            (link for link in first_result.collections["links"] if link["rel"] == "next"),
            None,
        )
        assert next_link is not None
        assert "token=" in next_link["href"]

        # Extract token from the next link
        token = next_link["href"].split("token=")[1]

        # Decode the token to verify apis are preserved
        decoded_token = collection_search_client._decode_token(token)

        # The token should contain the current state with the API URL
        assert "current" in decoded_token
        assert "https://api3.example.com" in decoded_token["current"]

        # Now follow the next link (simulate second request)
        # This should use the token which should have the apis preserved
        second_result = await collection_search_client.all_collections(
            request=mock_request, token=token
        )

        # Should have collections from page 2
        assert len(second_result.collections["collections"]) == 1
        collection_ids = [c["id"] for c in second_result.collections["collections"]]
        assert "api3-page2-collection-1" in collection_ids

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_all_apis_fail_strict_false(
        self, collection_search_client, mock_request
    ):
        """Test that all failing APIs returns empty collections with failed_apis."""
        respx.get("https://api1.example.com/collections").mock(
            return_value=Response(500, json={"error": "boom"})
        )
        respx.get("https://api2.example.com/collections").mock(
            return_value=Response(503, json={"error": "down"})
        )

        result = await collection_search_client.all_collections(request=mock_request)

        assert result.collections["collections"] == []
        assert result.collections["numberReturned"] == 0
        assert len(result.failed_apis) == 2
        assert "https://api1.example.com" in result.failed_apis
        assert "https://api2.example.com" in result.failed_apis

        # Only self link
        rels = {link["rel"] for link in result.collections["links"]}
        assert rels == {"self"}

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_network_timeout(
        self, collection_search_client, mock_request, sample_collections_response
    ):
        """Test that one timing-out API doesn't crash others."""
        import httpx

        respx.get("https://api1.example.com/collections").mock(
            side_effect=httpx.TimeoutException("Connection timed out")
        )
        respx.get("https://api2.example.com/collections").mock(
            return_value=Response(200, json=sample_collections_response)
        )

        result = await collection_search_client.all_collections(request=mock_request)

        assert len(result.collections["collections"]) == 2
        assert result.failed_apis == ["https://api1.example.com"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_malformed_json(
        self, collection_search_client, mock_request, sample_collections_response
    ):
        """Test that one malformed JSON response doesn't crash others."""
        respx.get("https://api1.example.com/collections").mock(
            return_value=Response(200, text="not-json")
        )
        respx.get("https://api2.example.com/collections").mock(
            return_value=Response(200, json=sample_collections_response)
        )

        result = await collection_search_client.all_collections(request=mock_request)

        assert len(result.collections["collections"]) == 2
        assert result.failed_apis == ["https://api1.example.com"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_pagination_with_failed_api(
        self, collection_search_client, mock_request, sample_collections_response
    ):
        """Test pagination state excludes failed APIs."""
        import copy

        api1_response = copy.deepcopy(sample_collections_response)
        api1_response["links"] = [
            {"rel": "self", "href": "https://api1.example.com/collections"},
            {
                "rel": "next",
                "href": "https://api1.example.com/collections?page=2",
            },
        ]

        api2_response = copy.deepcopy(sample_collections_response)
        api2_response["links"] = [
            {"rel": "self", "href": "https://api2.example.com/collections"},
        ]

        # api3 fails with 500
        respx.get("https://api1.example.com/collections").mock(
            return_value=Response(200, json=api1_response)
        )
        respx.get("https://api2.example.com/collections").mock(
            return_value=Response(200, json=api2_response)
        )
        respx.get("https://api3.example.com/collections").mock(
            return_value=Response(500, json={"error": "boom"})
        )

        result = await collection_search_client.all_collections(
            request=mock_request,
            apis=[
                "https://api1.example.com",
                "https://api2.example.com",
                "https://api3.example.com",
            ],
        )

        assert len(result.collections["collections"]) == 4
        assert "https://api3.example.com" in result.failed_apis

        # Next token should only include api1 (the one with a next link)
        next_link = next(
            (link for link in result.collections["links"] if link["rel"] == "next"),
            None,
        )
        assert next_link is not None
        token = next_link["href"].split("token=")[1]
        decoded = collection_search_client._decode_token(token)
        assert "https://api3.example.com" not in decoded["current"]
        assert "https://api1.example.com" in decoded["current"]
        # api2 didn't have a next link so won't be in next page's state
        assert "https://api2.example.com" not in decoded["current"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_empty_result_with_next_link(
        self, collection_search_client, mock_request
    ):
        """Test that empty collections with next link are handled correctly."""
        response_data = {
            "collections": [],
            "links": [
                {"rel": "self", "href": "https://api1.example.com/collections"},
                {
                    "rel": "next",
                    "href": "https://api1.example.com/collections?page=2",
                },
            ],
        }

        respx.get("https://api1.example.com/collections").mock(
            return_value=Response(200, json=response_data)
        )

        result = await collection_search_client.all_collections(
            request=mock_request, apis=["https://api1.example.com"]
        )

        assert result.collections["collections"] == []
        assert result.collections["numberReturned"] == 0
        assert result.failed_apis == []

        next_link = next(
            (link for link in result.collections["links"] if link["rel"] == "next"),
            None,
        )
        assert next_link is not None

    @pytest.mark.asyncio
    @respx.mock
    async def test_all_collections_empty_result_without_next_link(
        self, collection_search_client, mock_request
    ):
        """Test that empty collections without next link ends pagination."""
        response_data = {
            "collections": [],
            "links": [
                {"rel": "self", "href": "https://api1.example.com/collections"},
            ],
        }

        respx.get("https://api1.example.com/collections").mock(
            return_value=Response(200, json=response_data)
        )

        result = await collection_search_client.all_collections(
            request=mock_request, apis=["https://api1.example.com"]
        )

        assert result.collections["collections"] == []
        assert result.collections["numberReturned"] == 0
        next_link = next(
            (link for link in result.collections["links"] if link["rel"] == "next"),
            None,
        )
        assert next_link is None

    @pytest.mark.asyncio
    async def test_not_implemented_methods(self, collection_search_client):
        """Test that certain methods raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await collection_search_client.post_search()

        with pytest.raises(NotImplementedError):
            await collection_search_client.get_search()

        with pytest.raises(NotImplementedError):
            await collection_search_client.get_item()

        with pytest.raises(NotImplementedError):
            await collection_search_client.get_collection()

        with pytest.raises(NotImplementedError):
            await collection_search_client.item_collection()
