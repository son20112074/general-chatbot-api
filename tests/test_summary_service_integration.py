#!/usr/bin/env python3
"""
Test script for SummaryService integration in FileProcessingJob

This script tests the integration of SummaryService with the file processing job
to ensure AI summaries are generated correctly.
"""

import asyncio
import logging
import sys
import os
from pathlib import Path
from typing import Dict, Any

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parser.summary_service import SummaryService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_summary_service():
    """Test the SummaryService directly."""
    logger.info("🧪 Testing SummaryService...")
    
    summary_service = SummaryService()
    
    # Test content
    test_content = """
    Đây là một tài liệu mẫu để kiểm tra dịch vụ tóm tắt.
    Tài liệu này chứa thông tin quan trọng về dự án phát triển phần mềm.
    Dự án bao gồm việc xây dựng một hệ thống quản lý tác vụ với các tính năng:
    - Quản lý người dùng
    - Tạo và gán tác vụ
    - Theo dõi tiến độ
    - Báo cáo hiệu suất
    - Tích hợp với các hệ thống khác
    
    Dự án được thực hiện trong 6 tháng với đội ngũ 5 người.
    Ngân sách dự kiến là 500 triệu đồng.
    """
    
    # Test summarization
    result = summary_service.summarize_content(test_content, "txt", max_length=300)
    
    if result["success"]:
        logger.info("✅ SummaryService test passed!")
        logger.info(f"📝 Generated summary: {result['summary']}")
        logger.info(f"📊 Summary length: {result['summary_length']} characters")
        logger.info(f"📊 Original length: {result['original_length']} characters")
        return True
    else:
        logger.error(f"❌ SummaryService test failed: {result['error']}")
        return False


def test_parser_result_enhancement():
    """Test enhancing parser results with AI summaries."""
    logger.info("🧪 Testing parser result enhancement...")
    
    summary_service = SummaryService()
    
    # Mock parser result
    mock_parser_result = {
        "success": True,
        "content": "Đây là nội dung được trích xuất từ file Excel. File chứa dữ liệu về doanh thu của công ty trong năm 2024. Các cột dữ liệu bao gồm: tháng, doanh thu, chi phí, lợi nhuận. Tổng doanh thu năm 2024 là 10 tỷ đồng.",
        "summary": "Excel file with revenue data",
        "file_type": "excel"
    }
    
    # Test enhancement
    enhanced_result = summary_service.summarize_parser_result(mock_parser_result, ".xlsx")
    
    if enhanced_result.get("has_ai_summary"):
        logger.info("✅ Parser result enhancement test passed!")
        logger.info(f"📝 Enhanced summary: {enhanced_result['summary']}")
        return True
    else:
        logger.error(f"❌ Parser result enhancement test failed: {enhanced_result.get('ai_summary_error', 'Unknown error')}")
        return False


def test_content_extraction():
    """Test content extraction from various result formats."""
    logger.info("🧪 Testing content extraction...")
    
    summary_service = SummaryService()
    
    # Test different result formats
    test_cases = [
        {
            "name": "String content",
            "result": {"content": "Đây là nội dung văn bản."},
            "expected": "Đây là nội dung văn bản."
        },
        {
            "name": "List content",
            "result": {"content": ["Dòng 1", "Dòng 2", "Dòng 3"]},
            "expected": "Dòng 1\nDòng 2\nDòng 3"
        },
        {
            "name": "Dict content",
            "result": {"data": {"title": "Tiêu đề", "body": "Nội dung"}},
            "expected": "{'title': 'Tiêu đề', 'body': 'Nội dung'}"
        },
        {
            "name": "Empty result",
            "result": {},
            "expected": ""
        }
    ]
    
    all_passed = True
    for test_case in test_cases:
        extracted = summary_service._extract_content_from_result(test_case["result"])
        if extracted == test_case["expected"]:
            logger.info(f"✅ {test_case['name']}: PASSED")
        else:
            logger.error(f"❌ {test_case['name']}: FAILED (expected: {test_case['expected']}, got: {extracted})")
            all_passed = False
    
    return all_passed


async def main():
    """Run all tests."""
    logger.info("🚀 Starting SummaryService integration tests...")
    
    tests = [
        ("SummaryService Direct Test", test_summary_service),
        ("Parser Result Enhancement Test", test_parser_result_enhancement),
        ("Content Extraction Test", test_content_extraction)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running: {test_name}")
        logger.info(f"{'='*50}")
        
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                passed += 1
                logger.info(f"✅ {test_name}: PASSED")
            else:
                logger.error(f"❌ {test_name}: FAILED")
                
        except Exception as e:
            logger.error(f"❌ {test_name}: ERROR - {str(e)}")
    
    logger.info(f"\n{'='*50}")
    logger.info(f"📊 Test Results: {passed}/{total} tests passed")
    logger.info(f"{'='*50}")
    
    if passed == total:
        logger.info("🎉 All tests passed! SummaryService integration is working correctly.")
    else:
        logger.error("❌ Some tests failed. Please check the implementation.")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
