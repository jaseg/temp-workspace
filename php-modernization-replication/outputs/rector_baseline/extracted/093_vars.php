<?php
/**
 * Creates common globals for the rest of WordPress
 *
 * Sets $pagenow global which is the current page. Checks
 * for the browser to set which one is currently being used.
 *
 * Detects which user environment WordPress is being used on.
 * Only attempts to check for Apache, Nginx and IIS -- three web
 * servers with known pretty permalink capability.
 *
 * Note: Though Nginx is detected, WordPress does not currently
 * generate rewrite rules for it. See http://codex.wordpress.org/Nginx
 *
 * @package WordPress
 */

global $pagenow,
	$is_lynx, $is_gecko, $is_winIE, $is_macIE, $is_opera, $is_NS4, $is_safari, $is_chrome, $is_iphone, $is_IE,
	$is_apache, $is_IIS, $is_iis7, $is_nginx;

// On which page are we ?
if ( is_admin() ) {
	// wp-admin pages are checked more carefully
	if ( is_network_admin() )
		preg_match('#/wp-admin/network/?(.*?)$#i', (string) $_SERVER['PHP_SELF'], $self_matches);
	elseif ( is_user_admin() )
		preg_match('#/wp-admin/user/?(.*?)$#i', (string) $_SERVER['PHP_SELF'], $self_matches);
	else
		preg_match('#/wp-admin/?(.*?)$#i', (string) $_SERVER['PHP_SELF'], $self_matches);
	$pagenow = $self_matches[1];
	$pagenow = trim($pagenow, '/');
	$pagenow = preg_replace('#\?.*?$#', '', $pagenow);
	if ( '' === $pagenow || 'index' === $pagenow || 'index.php' === $pagenow ) {
		$pagenow = 'index.php';
	} else {
		preg_match('#(.*?)(/|$)#', (string) $pagenow, $self_matches);
		$pagenow = strtolower($self_matches[1]);
		if ( !str_ends_with($pagenow, '.php') )
			$pagenow .= '.php'; // for Options +Multiviews: /wp-admin/themes/index.php (themes.php is queried)
	}
} else {
	if ( preg_match('#([^/]+\.php)([?/].*?)?$#i', (string) $_SERVER['PHP_SELF'], $self_matches) )
		$pagenow = strtolower($self_matches[1]);
	else
		$pagenow = 'index.php';
}
unset($self_matches);

// Simple browser detection
$is_lynx = $is_gecko = $is_winIE = $is_macIE = $is_opera = $is_NS4 = $is_safari = $is_chrome = $is_iphone = false;

if ( isset($_SERVER['HTTP_USER_AGENT']) ) {
	if ( str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Lynx') ) {
		$is_lynx = true;
	} elseif ( stripos((string) $_SERVER['HTTP_USER_AGENT'], 'chrome') !== false ) {
		if ( stripos( (string) $_SERVER['HTTP_USER_AGENT'], 'chromeframe' ) !== false ) {
			$is_admin = is_admin();
			/**
			 * Filter whether Google Chrome Frame should be used, if available.
			 *
			 * @since 3.2.0
			 *
			 * @param bool $is_admin Whether to use the Google Chrome Frame. Default is the value of is_admin().
			 */
			if ( $is_chrome = apply_filters( 'use_google_chrome_frame', $is_admin ) )
				header( 'X-UA-Compatible: chrome=1' );
			$is_winIE = ! $is_chrome;
		} else {
			$is_chrome = true;
		}
	} elseif ( stripos((string) $_SERVER['HTTP_USER_AGENT'], 'safari') !== false ) {
		$is_safari = true;
	} elseif ( ( str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'MSIE') || str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Trident') ) && str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Win') ) {
		$is_winIE = true;
	} elseif ( str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'MSIE') && str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Mac') ) {
		$is_macIE = true;
	} elseif ( str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Gecko') ) {
		$is_gecko = true;
	} elseif ( str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Opera') ) {
		$is_opera = true;
	} elseif ( str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Nav') && str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Mozilla/4.') ) {
		$is_NS4 = true;
	}
}

if ( $is_safari && stripos((string) $_SERVER['HTTP_USER_AGENT'], 'mobile') !== false )
	$is_iphone = true;

$is_IE = ( $is_macIE || $is_winIE );

// Server detection

/**
 * Whether the server software is Apache or something else
 * @global bool $is_apache
 */
$is_apache = (str_contains((string) $_SERVER['SERVER_SOFTWARE'], 'Apache') || str_contains((string) $_SERVER['SERVER_SOFTWARE'], 'LiteSpeed'));

/**
 * Whether the server software is Nginx or something else
 * @global bool $is_nginx
 */
$is_nginx = (str_contains((string) $_SERVER['SERVER_SOFTWARE'], 'nginx'));

/**
 * Whether the server software is IIS or something else
 * @global bool $is_IIS
 */
$is_IIS = !$is_apache && (str_contains((string) $_SERVER['SERVER_SOFTWARE'], 'Microsoft-IIS') || str_contains((string) $_SERVER['SERVER_SOFTWARE'], 'ExpressionDevServer'));

/**
 * Whether the server software is IIS 7.X or greater
 * @global bool $is_iis7
 */
$is_iis7 = $is_IIS && intval( substr( (string) $_SERVER['SERVER_SOFTWARE'], strpos( (string) $_SERVER['SERVER_SOFTWARE'], 'Microsoft-IIS/' ) + 14 ) ) >= 7;

/**
 * Test if the current browser runs on a mobile device (smart phone, tablet, etc.)
 *
 * @return bool true|false
 */
function wp_is_mobile() {
	static $is_mobile;

	if ( isset($is_mobile) )
		return $is_mobile;

	if ( empty($_SERVER['HTTP_USER_AGENT']) ) {
		$is_mobile = false;
	} elseif ( str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Mobile') // many mobile devices (all iPhone, iPad, etc.)
		|| str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Android')
		|| str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Silk/')
		|| str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Kindle')
		|| str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'BlackBerry')
		|| str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Opera Mini')
		|| str_contains((string) $_SERVER['HTTP_USER_AGENT'], 'Opera Mobi') ) {
			$is_mobile = true;
	} else {
		$is_mobile = false;
	}

	return $is_mobile;
}
