from src.agents.research_agent import research_topic

if __name__ == "__main__":

    result = research_topic(
        topic="AI content marketing trends",
        target_audience="Marketing professionals",
        num_results=5,
    )

    print("\nRESEARCH SUMMARY")
    print(result["research_summary"])

    print("\nFINDINGS")
    for finding in result["findings"]:
        print(f"\nClaim: {finding['claim']}")
        print(f"Explanation: {finding['explanation']}")
        print(f"Sources: {finding['source_urls']}")

    print("\nSOURCES")
    for source in result["sources"]:
        print(source["title"])
        print(source["url"])