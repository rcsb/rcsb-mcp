"""Sequence Coordinates API as MCP tools.

- The Sequence Coordinates API (https://sequence-coordinates.rcsb.org/graphql)
is used to map alignments and positional annotations between sequence reference systems
(`UNIPROT`, `NCBI_PROTEIN`, `NCBI_GENOME`, `PDB_ENTITY`, `PDB_INSTANCE`).

"""

from graphql_mcp.server import GraphQLMCP

server = GraphQLMCP.from_remote_url(
    url="https://sequence-coordinates.rcsb.org/graphql",
    name="RCSB PDB Sequence Coordinates API",
    allow_mutations=False,
    graphql_http_kwargs={
        "graphiql_example_query": """\
{
  alignments(
    from:PDB_ENTITY,
    to:NCBI_PROTEIN,
    queryId:"AF_AFP68871F1_1"
  ){
    query_sequence
    target_alignments {
      target_id
      target_sequence
      coverage{
        query_coverage
        query_length
        target_coverage
        target_length
      }
      aligned_regions {
        query_begin
        query_end
        target_begin
        target_end
      }
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