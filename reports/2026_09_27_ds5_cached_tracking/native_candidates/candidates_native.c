/* Research-only candidate-budget build of the frozen TG11 native engine.
 *
 * The build wrapper supplies LEO_PRESENCE_CANDIDATES as either one or two.
 * Keeping this as an include-only translation unit preserves every other
 * operation and ABI in the frozen engine while producing a distinct binary.
 */
#include "../tg11/tg11_native.c"
