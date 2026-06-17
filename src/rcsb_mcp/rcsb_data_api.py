"""Remote API - wraps a public GraphQL API as MCP tools.

Demonstrates:
- GraphQLMCP.from_remote_url() to introspect and wrap any GraphQL endpoint
- Auto-generated MCP tools from a remote schema
- Read-only access (allow_mutations=False)
- Running via stdio for Claude Desktop compatibility

"""

from graphql_mcp.server import GraphQLMCP

server = GraphQLMCP.from_remote_url(
    url="https://data.rcsb.org/graphql",
    name="RCSB PDB Data API",
    allow_mutations=False,
    graphql_http_kwargs={
        "graphiql_example_query": """\
{
  entries(entry_ids: ["1STP", "2JEF", "1CDG"]) {
    rcsb_id
    struct {
      title
    }
    exptl {
      method
    }
  }
}""",
    },
)

def main():
    server.run()

if __name__ == "__main__":
    # server.run() automatically uses stdio transport,
    # making it perfectly compatible with Claude Desktop.
    main()