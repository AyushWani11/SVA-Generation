// Round-Robin Arbiter with 4 requestors
// Signals: clk, rst_n, req[3:0], grant[3:0], active

module round_robin_arbiter #(
    parameter NUM_REQ = 4
) (
    input  logic                clk,
    input  logic                rst_n,
    input  logic [NUM_REQ-1:0]  req,
    output logic [NUM_REQ-1:0]  grant,
    output logic                active
);

    // State: last granted requestor (one-hot encoded priority pointer)
    logic [NUM_REQ-1:0] priority_mask;
    logic [NUM_REQ-1:0] masked_req;
    logic [NUM_REQ-1:0] unmasked_grant;
    logic [NUM_REQ-1:0] masked_grant;
    logic               any_masked_req;

    // Masked request: only consider requests with lower priority than last grant
    assign masked_req = req & priority_mask;
    assign any_masked_req = |masked_req;

    // Priority encoder for masked requests (lowest bit = highest priority)
    always_comb begin
        masked_grant = '0;
        for (int i = 0; i < NUM_REQ; i++) begin
            if (masked_req[i]) begin
                masked_grant = (1 << i);
                break;
            end
        end
    end

    // Priority encoder for unmasked requests (fallback)
    always_comb begin
        unmasked_grant = '0;
        for (int i = 0; i < NUM_REQ; i++) begin
            if (req[i]) begin
                unmasked_grant = (1 << i);
                break;
            end
        end
    end

    // Grant selection: prefer masked (round-robin) over unmasked
    logic [NUM_REQ-1:0] next_grant;
    assign next_grant = any_masked_req ? masked_grant : unmasked_grant;

    // Register grant output
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            grant <= '0;
            priority_mask <= {NUM_REQ{1'b1}};
        end else if (|req) begin
            grant <= next_grant;
            // Update priority mask: all bits above granted position
            priority_mask <= ~((next_grant << 1) - 1) | next_grant;
        end else begin
            grant <= '0;
        end
    end

    // Active signal: any grant is active
    assign active = |grant;

endmodule
