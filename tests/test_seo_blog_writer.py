
import json
import unittest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage

from src.agents.blog_writer import (
    write_seo_blog,
    format_blog_markdown,
    parse_blog_response,
    validate_blog_data,
)


SAMPLE_BLOG_DATA = {
    "seo_title": "A Practical Guide to AI Content Marketing",
    "meta_description": "Learn how AI can improve content research, planning, and creation.",
    "url_slug": "ai-content-marketing-guide",
    "primary_keyword": "AI content marketing",
    "secondary_keywords": [
        "AI content strategy",
        "AI content creation",
        "content marketing automation",
    ],
    "search_intent": "Informational",
    "article_outline": [
        {
            "level": "H2",
            "heading": "What Is AI Content Marketing?"
        },
        {
            "level": "H2",
            "heading": "Benefits of AI in Content Marketing"
        },
        {
            "level": "H2",
            "heading": "How to Build an AI Content Strategy"
        },
    ],
    "blog_article": """
## What Is AI Content Marketing?

AI content marketing uses artificial intelligence to support content
research, planning, creation, and optimization.

## Benefits of AI in Content Marketing

AI tools can help teams organize research and accelerate content workflows.

## How to Build an AI Content Strategy

Start with clear objectives, understand your audience, and review
AI-generated content before publishing.
""",
    "faqs": [
        {
            "question": "What is AI content marketing?",
            "answer": "It uses AI technologies to support content marketing activities."
        },
        {
            "question": "Can AI replace content writers?",
            "answer": "AI can assist writers, but human review and editorial judgment remain important."
        },
    ],
    "call_to_action": "Explore how AI can support your content strategy.",
    "sources": [
        {
            "title": "Example Research Source",
            "url": "https://example.com/ai-content-marketing"
        }
    ],
}


class TestSEOBlogWriter(unittest.TestCase):

    def test_parse_blog_response(self):
        response = json.dumps(SAMPLE_BLOG_DATA)

        result = parse_blog_response(response)

        self.assertEqual(
            result["seo_title"],
            SAMPLE_BLOG_DATA["seo_title"]
        )

    def test_validate_blog_data(self):
        validate_blog_data(SAMPLE_BLOG_DATA)

    def test_invalid_blog_data(self):
        invalid_data = {
            "seo_title": "Test blog"
        }

        with self.assertRaises(ValueError):
            validate_blog_data(invalid_data)

    def test_format_blog_markdown(self):
        markdown = format_blog_markdown(SAMPLE_BLOG_DATA)

        # SEO title, article, FAQs, call to action and sources are shown to the user.
        self.assertTrue(markdown.startswith("# A Practical Guide to AI Content Marketing"))
        self.assertIn("## What Is AI Content Marketing?", markdown)
        self.assertIn("## Frequently Asked Questions", markdown)
        self.assertIn("### Can AI replace content writers?", markdown)
        self.assertIn("## Call to Action", markdown)
        self.assertIn("## Sources", markdown)
        self.assertIn("[Example Research Source](https://example.com/ai-content-marketing)", markdown)

        # SEO details and the outline stay in the blog data, not in the draft.
        self.assertNotIn("## SEO Details", markdown)
        self.assertNotIn("## Article Outline", markdown)
        self.assertNotIn("## Complete Blog Article", markdown)



    @patch("src.agents.blog_writer.stream_text")
    @patch("src.agents.blog_writer.build_seo_blog_writer")
    def test_write_seo_blog(self, mock_build_writer, mock_stream_text):
        fake_agent = MagicMock()

        # The agent returns the plan; the article is streamed separately.
        plan = {key: value for key, value in SAMPLE_BLOG_DATA.items() if key != "blog_article"}

        fake_agent.stream.return_value = iter([
            {"model": {"messages": [AIMessage(content=json.dumps(plan))]}}
        ])
        mock_build_writer.return_value = fake_agent
        mock_stream_text.return_value = iter([SAMPLE_BLOG_DATA["blog_article"]])

        result = write_seo_blog(
            topic="AI content marketing",
            target_audience="Small business owners",
            tone="Professional",
            keywords=["AI content marketing"],
            objective="Educate readers",
        )

        assert result["seo_title"] == SAMPLE_BLOG_DATA["seo_title"]
        assert result["primary_keyword"] == SAMPLE_BLOG_DATA["primary_keyword"]
        assert result["blog_article"] == SAMPLE_BLOG_DATA["blog_article"].strip()
        fake_agent.stream.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
