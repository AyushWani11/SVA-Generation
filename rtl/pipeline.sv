// Simple 3-Stage Pipelined Datapath (Fetch -> Execute -> Writeback)
// Supports ADD, SUB, AND, OR operations
// Signals: clk, rst_n, opcode, operand_a, operand_b, result, result_valid, stall, flush

module pipeline_datapath #(
    parameter DATA_WIDTH = 16
) (
    input  logic                   clk,
    input  logic                   rst_n,
    input  logic [1:0]             opcode,      // 00=ADD, 01=SUB, 10=AND, 11=OR
    input  logic [DATA_WIDTH-1:0]  operand_a,
    input  logic [DATA_WIDTH-1:0]  operand_b,
    input  logic                   valid_in,    // Input valid
    input  logic                   stall,       // Pipeline stall
    input  logic                   flush,       // Pipeline flush
    output logic [DATA_WIDTH-1:0]  result,
    output logic                   result_valid
);

    // Opcode encoding
    localparam OP_ADD = 2'b00;
    localparam OP_SUB = 2'b01;
    localparam OP_AND = 2'b10;
    localparam OP_OR  = 2'b11;

    // Stage 1: Fetch/Decode registers
    logic [1:0]             s1_opcode;
    logic [DATA_WIDTH-1:0]  s1_operand_a;
    logic [DATA_WIDTH-1:0]  s1_operand_b;
    logic                   s1_valid;

    // Stage 2: Execute registers
    logic [DATA_WIDTH-1:0]  s2_result;
    logic                   s2_valid;

    // Stage 3: Writeback (output)
    logic [DATA_WIDTH-1:0]  s3_result;
    logic                   s3_valid;

    // Stage 1: Fetch/Decode
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s1_opcode   <= '0;
            s1_operand_a <= '0;
            s1_operand_b <= '0;
            s1_valid    <= 1'b0;
        end else if (flush) begin
            s1_valid <= 1'b0;
        end else if (!stall) begin
            s1_opcode   <= opcode;
            s1_operand_a <= operand_a;
            s1_operand_b <= operand_b;
            s1_valid    <= valid_in;
        end
    end

    // Stage 2: Execute
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s2_result <= '0;
            s2_valid  <= 1'b0;
        end else if (flush) begin
            s2_valid <= 1'b0;
        end else if (!stall) begin
            s2_valid <= s1_valid;
            case (s1_opcode)
                OP_ADD: s2_result <= s1_operand_a + s1_operand_b;
                OP_SUB: s2_result <= s1_operand_a - s1_operand_b;
                OP_AND: s2_result <= s1_operand_a & s1_operand_b;
                OP_OR:  s2_result <= s1_operand_a | s1_operand_b;
            endcase
        end
    end

    // Stage 3: Writeback
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s3_result <= '0;
            s3_valid  <= 1'b0;
        end else if (flush) begin
            s3_valid <= 1'b0;
        end else if (!stall) begin
            s3_result <= s2_result;
            s3_valid  <= s2_valid;
        end
    end

    // Output
    assign result       = s3_result;
    assign result_valid = s3_valid;

endmodule
