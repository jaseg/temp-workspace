// Suspends or resumes an AudioContext so that the latest request wins.
//
// Firefox can settle a suspend() that was immediately followed by resume() after the resume, which leaves the
// context suspended (and the song silent) although the last call asked for it to run. So every settled call
// compares the context's state with the latest request and applies it again if needed. The first call happens
// synchronously, so a resume made inside a click still counts as made during the user gesture.
const MAX_RETRIES = 3;

export function setContextRunning(context, running) {
	context.wantRunning = running;
	const apply = retries => () => {
		if (retries <= 0 || context.state === 'closed') return;
		if (context.wantRunning && context.state === 'suspended') context.resume().then(apply(retries - 1), () => {});
		else if (!context.wantRunning && context.state === 'running') context.suspend().then(apply(retries - 1), () => {});
	};
	(running ? context.resume() : context.suspend()).then(apply(MAX_RETRIES), () => {});
}
