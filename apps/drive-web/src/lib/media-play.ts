/**
 * Start playback on a media element, retrying once when the browser rejects the
 * pending play() with AbortError ("play() request was interrupted by a call to
 * pause()"). That rejection only says the previous play promise was superseded,
 * not that the element cannot play; the element is still attached and the
 * intent to play is unchanged, so one retry is the correct recovery. Any other
 * rejection (NotAllowedError, NotSupportedError, decode errors) propagates.
 */
export async function playWithAbortRetry(
	video: Pick<HTMLVideoElement, 'play'>,
	retryDelayMs = 50
): Promise<void> {
	try {
		await video.play();
	} catch (error) {
		const aborted =
			typeof error === 'object' && error !== null && 'name' in error && error.name === 'AbortError';
		if (!aborted) throw error;
		const { promise, resolve } = Promise.withResolvers<void>();
		setTimeout(resolve, retryDelayMs);
		await promise;
		await video.play();
	}
}
