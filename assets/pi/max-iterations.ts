/**
 * Max Iterations Extension
 *
 * Limits the number of agent iterations (turns) per prompt.
 * An iteration is one LLM call plus any tool use that follows.
 *
 * When the limit is reached, all subsequent tool calls are blocked.
 * This reliably stops the agent loop because without tool results
 * to process, the loop exits naturally after the LLM responds with
 * text only.
 *
 * Usage:
 *   pi --max-iterations 5
 *   pi --max-iterations 3 -p "Refactor the auth module"
 *   pi -e ./max-iterations.ts --max-iterations 10
 *
 * Install:
 *   cp max-iterations.ts ~/.pi/agent/extensions/max-iterations.ts
 *   Then just use: pi --max-iterations 5
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function maxIterationsExtension(pi: ExtensionAPI) {
	pi.registerFlag("max-iterations", {
		description: "Max agent iterations per prompt (1 LLM call + tool use = 1 iteration)",
		type: "string",
	});

	let maxIterations: number | null = null;
	let limitReached = false;

	pi.on("session_start", async (_event, ctx) => {
		const flagValue = pi.getFlag("max-iterations");
		if (flagValue !== undefined && flagValue !== "") {
			const parsed = parseInt(flagValue as string, 10);
			if (Number.isNaN(parsed) || parsed < 1) {
				ctx.ui.notify(
					`--max-iterations: invalid value "${flagValue}". Must be a positive integer.`,
					"error",
				);
				maxIterations = null;
			} else {
				maxIterations = parsed;
				ctx.ui.setStatus(
					"max-iterations",
					ctx.ui.theme.fg("accent", `max-iter: ${maxIterations}`),
				);
			}
		} else {
			maxIterations = null;
		}

		limitReached = false;
		ctx.ui.setStatus("max-iterations", maxIterations
			? ctx.ui.theme.fg("accent", `max-iter: ${maxIterations}`)
			: undefined);
	});

	// Reset per user prompt
	pi.on("agent_start", async () => {
		limitReached = false;
	});

	// Block all tool calls once the limit is reached.
	// This is the primary mechanism for stopping the agent: the loop
	// exits when there are no tool results to drive the next turn.
	pi.on("tool_call", async (_event, ctx) => {
		if (!limitReached) return;

		return {
			block: true,
			reason: `Max iterations reached (${maxIterations}). No further tool calls allowed.`,
		};
	});

	pi.on("turn_end", async (event, ctx) => {
		if (maxIterations === null) return;

		const completed = event.turnIndex + 1;

		if (completed >= maxIterations && !limitReached) {
			limitReached = true;
			ctx.ui.notify(
				`Max iterations reached (${maxIterations}). Further tool calls will be blocked.`,
				"warning",
			);
		}

		if (limitReached) {
			ctx.ui.setStatus(
				"max-iterations",
				ctx.ui.theme.fg("warning", `iter: ${completed}/${maxIterations} (limit)`),
			);
		} else {
			ctx.ui.setStatus(
				"max-iterations",
				ctx.ui.theme.fg("accent", `iter: ${completed}/${maxIterations}`),
			);
		}
	});
}
