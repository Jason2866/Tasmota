import os

Import("env")

env.BuildSources(
    os.path.join("$BUILD_DIR", "external", "build"),
    os.path.join("$PROJECT_DIR", "external", "sources")
)