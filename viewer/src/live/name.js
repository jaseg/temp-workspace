// The viewer's name: suggested as two random words, remembered once the viewer types one.
import {EVEN, ODD} from './words';

const NAME_KEY = 'bslive.name';

export const MAX_NAME_LENGTH = 32; // the server cuts names to this

export function loadName() {
	try {
		return localStorage.getItem(NAME_KEY) || '';
	} catch (e) {
		return '';
	}
}

export function saveName(name) {
	try {
		if (name) localStorage.setItem(NAME_KEY, name);
		else localStorage.removeItem(NAME_KEY);
	} catch (e) {
		// Storage unavailable: the field just starts empty next time.
	}
}

/** Whitespace runs as single spaces, trimmed. The server cleans up the rest. */
export function tidyName(name) {
	return name.trim().replace(/\s+/g, ' ');
}

const capitalize = word => word.charAt(0).toUpperCase() + word.slice(1);

/** Two random words from the PGP word list (an even and an odd one), e.g. "Aztec Istanbul". */
export function randomName() {
	const bytes = crypto.getRandomValues(new Uint8Array(2));
	return `${capitalize(EVEN[bytes[0]])} ${capitalize(ODD[bytes[1]])}`;
}
