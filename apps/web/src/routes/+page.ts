import { redirect } from '@sveltejs/kit';

// The standalone digital-twin dashboard is retired: the twin now lives
// inside the drive experience (Drive | Twin toggle on /drive).
export function load() {
	redirect(307, '/drive?view=twin');
}
