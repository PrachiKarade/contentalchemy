from src.core.workflow import build_workflow

def test_workflow_compiles():
    graph = build_workflow()
    assert graph is not None

    print("Workflow compiled successfully!")

if __name__ == "__main__":
    test_workflow_compiles()