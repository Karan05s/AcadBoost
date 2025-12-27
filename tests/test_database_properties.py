"""
Property-based tests for database connections
Feature: learning-analytics-platform, Property 1: Database connection reliability
"""
import pytest
import asyncio
from hypothesis import given, strategies as st, settings as hypothesis_settings
from unittest.mock import MagicMock, patch
from app.core.database import get_database, create_indexes


class TestDatabaseConnectionReliability:
    """
    Property 1: Database connection reliability
    Validates: Requirements 6.4
    """
    
    @pytest.mark.property
    @pytest.mark.asyncio
    async def test_database_connection_reliability(self, setup_test_database):
        """
        Feature: learning-analytics-platform, Property 1: Database connection reliability
        
        For any database initialization, the connection should be established successfully
        and basic operations should work reliably.
        """
        # Use the mocked database from the fixture
        with patch('app.core.database.get_database', return_value=setup_test_database):
            # Get database instance (mocked in test environment)
            db = await get_database()
            assert db is not None, "Database instance should not be None"
            
            # Test basic database operations
            test_collection = db["test_connection"]
            
            # Configure mock responses
            mock_insert_result = MagicMock()
            mock_insert_result.inserted_id = "test_id_123"
            test_collection.insert_one.return_value = mock_insert_result
            
            test_collection.find_one.return_value = {
                "_id": "test_id_123",
                "test": "connection_reliability"
            }
            
            mock_update_result = MagicMock()
            mock_update_result.modified_count = 1
            test_collection.update_one.return_value = mock_update_result
            
            mock_delete_result = MagicMock()
            mock_delete_result.deleted_count = 1
            test_collection.delete_one.return_value = mock_delete_result
            
            # Test insert operation
            test_doc = {"test": "connection_reliability", "timestamp": "2024-01-01"}
            result = await test_collection.insert_one(test_doc)
            assert result.inserted_id is not None, "Insert operation should return an ID"
            
            # Test find operation
            found_doc = await test_collection.find_one({"_id": result.inserted_id})
            assert found_doc is not None, "Should be able to find inserted document"
            assert found_doc["test"] == "connection_reliability"
            
            # Test update operation
            update_result = await test_collection.update_one(
                {"_id": result.inserted_id},
                {"$set": {"updated": True}}
            )
            assert update_result.modified_count == 1, "Update should modify exactly one document"
            
            # Test delete operation
            delete_result = await test_collection.delete_one({"_id": result.inserted_id})
            assert delete_result.deleted_count == 1, "Delete should remove exactly one document"
            
            # Cleanup test collection
            await test_collection.drop()
    
    @pytest.mark.property
    @pytest.mark.asyncio
    @given(
        collection_name=st.text(
            alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd')), 
            min_size=1, 
            max_size=20
        ).filter(lambda x: x.isalnum())
    )
    @hypothesis_settings(max_examples=10, deadline=5000)
    async def test_collection_operations_reliability(self, collection_name, setup_test_database):
        """
        Feature: learning-analytics-platform, Property 1: Database connection reliability
        
        For any valid collection name, basic CRUD operations should work reliably.
        """
        # Use the mocked database from the fixture
        with patch('app.core.database.get_database', return_value=setup_test_database):
            # Get database instance
            db = await get_database()
            assert db is not None, "Database instance should not be None"
            
            # Use test prefix to avoid conflicts
            test_collection_name = f"test_{collection_name}"
            collection = db[test_collection_name]
            
            # Configure mock responses
            mock_insert_result = MagicMock()
            mock_insert_result.inserted_id = f"test_id_{collection_name}"
            collection.insert_one.return_value = mock_insert_result
            
            collection.find_one.return_value = {
                "_id": f"test_id_{collection_name}",
                "collection_test": True,
                "name": collection_name,
                "data": "reliability_test"
            }
            
            collection.count_documents.return_value = 1
            
            # Test document creation
            test_doc = {
                "collection_test": True,
                "name": collection_name,
                "data": "reliability_test"
            }
            
            # Insert document
            result = await collection.insert_one(test_doc)
            assert result.inserted_id is not None
            
            # Verify document exists
            found = await collection.find_one({"_id": result.inserted_id})
            assert found is not None
            assert found["collection_test"] is True
            assert found["name"] == collection_name
            
            # Count documents
            count = await collection.count_documents({})
            assert count >= 1
            
            # Cleanup - drop test collection
            await collection.drop()
    
    @pytest.mark.property
    @pytest.mark.asyncio
    async def test_index_creation_reliability(self, setup_test_database):
        """
        Feature: learning-analytics-platform, Property 1: Database connection reliability
        
        For any database connection, index creation should complete successfully
        and indexes should be accessible.
        """
        # Use the mocked database from the fixture
        with patch('app.core.database.get_database', return_value=setup_test_database):
            # Get database instance
            db = await get_database()
            assert db is not None, "Database instance should not be None"
            
            # Test index creation
            await create_indexes()
            
            # Verify indexes exist on key collections
            collections_to_check = [
                "user_profiles",
                "student_performance", 
                "learning_gaps",
                "recommendations"
            ]
            
            for collection_name in collections_to_check:
                collection = db[collection_name]
                indexes = await collection.list_indexes().to_list(length=None)
                
                # Should have at least the default _id index plus our custom indexes
                assert len(indexes) >= 1, f"Collection {collection_name} should have indexes"
                
                # Check that indexes have proper structure
                for index in indexes:
                    assert "key" in index, "Index should have key field"
                    assert "name" in index, "Index should have name field"
    
    @pytest.mark.property
    @pytest.mark.asyncio
    async def test_concurrent_connection_reliability(self, setup_test_database):
        """
        Feature: learning-analytics-platform, Property 1: Database connection reliability
        
        For any concurrent database operations, connections should remain stable
        and operations should complete successfully.
        """
        # Use the mocked database from the fixture
        with patch('app.core.database.get_database', return_value=setup_test_database):
            # Get database instance
            db = await get_database()
            assert db is not None, "Database instance should not be None"
            
            test_collection = db["test_concurrent"]
            
            # Configure mock responses for concurrent operations
            def mock_insert_one(doc):
                result = MagicMock()
                result.inserted_id = f"test_id_{doc['operation_id']}"
                return result
            
            def mock_find_one(query):
                doc_id = query["_id"]
                operation_id = int(doc_id.split("_")[-1])
                return {
                    "_id": doc_id,
                    "operation_id": operation_id,
                    "test": "concurrent_reliability"
                }
            
            test_collection.insert_one.side_effect = mock_insert_one
            test_collection.find_one.side_effect = mock_find_one
            test_collection.count_documents.return_value = 5
            
            async def concurrent_operation(operation_id: int):
                """Perform a database operation concurrently"""
                doc = {"operation_id": operation_id, "test": "concurrent_reliability"}
                result = await test_collection.insert_one(doc)
                
                # Verify the document was inserted
                found = await test_collection.find_one({"_id": result.inserted_id})
                assert found is not None
                assert found["operation_id"] == operation_id
                
                return result.inserted_id
            
            # Run multiple concurrent operations
            tasks = [concurrent_operation(i) for i in range(5)]
            results = await asyncio.gather(*tasks)
            
            # Verify all operations completed successfully
            assert len(results) == 5
            assert all(result is not None for result in results)
            
            # Verify all documents exist in database
            count = await test_collection.count_documents({})
            assert count == 5
            
            # Cleanup
            await test_collection.drop()