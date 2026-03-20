// Generic FSM Controller (Traffic Light Controller)
// States: IDLE -> GREEN -> YELLOW -> RED -> IDLE
// Signals: clk, rst_n, start, sensor, timer_expired, state, light_green, light_yellow, light_red

module fsm_controller (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       start,          // Start signal
    input  logic       sensor,         // Vehicle sensor
    input  logic       timer_expired,  // Timer expiration
    output logic [1:0] state,          // Current state encoding
    output logic       light_green,
    output logic       light_yellow,
    output logic       light_red,
    output logic       timer_start     // Signal to start timer
);

    // State encoding
    typedef enum logic [1:0] {
        IDLE   = 2'b00,
        GREEN  = 2'b01,
        YELLOW = 2'b10,
        RED    = 2'b11
    } state_t;

    state_t current_state, next_state;

    // State register
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            current_state <= IDLE;
        else
            current_state <= next_state;
    end

    // Next state logic
    always_comb begin
        next_state = current_state;
        timer_start = 1'b0;

        case (current_state)
            IDLE: begin
                if (start) begin
                    next_state = GREEN;
                    timer_start = 1'b1;
                end
            end

            GREEN: begin
                if (timer_expired || !sensor) begin
                    next_state = YELLOW;
                    timer_start = 1'b1;
                end
            end

            YELLOW: begin
                if (timer_expired) begin
                    next_state = RED;
                    timer_start = 1'b1;
                end
            end

            RED: begin
                if (timer_expired) begin
                    next_state = IDLE;
                end
            end

            default: next_state = IDLE;
        endcase
    end

    // Output logic
    assign state        = current_state;
    assign light_green  = (current_state == GREEN);
    assign light_yellow = (current_state == YELLOW);
    assign light_red    = (current_state == RED);

endmodule
