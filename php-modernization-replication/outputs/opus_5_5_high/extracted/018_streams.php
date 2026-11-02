<?php
/**
 * Classes, which help reading streams of data from files.
 * Based on the classes from Danilo Segan <danilo@kvota.net>
 *
 * @version $Id: streams.php 718 2012-10-31 00:32:02Z nbachiyski $
 * @package pomo
 * @subpackage streams
 */

if ( ! class_exists( 'POMO_Reader', false ) ) :
class POMO_Reader {

	public $endian = 'little';
	public $_post = '';
	public $is_overloaded = false;
	public $_pos = 0;

	public function __construct() {
		$this->is_overloaded = ( ( (int) ini_get( 'mbstring.func_overload' ) & 2 ) !== 0 ) && function_exists( 'mb_substr' );
		$this->_pos          = 0;
	}

	/**
	 * PHP4-style constructor kept for backwards compatibility.
	 *
	 * @deprecated Use __construct() instead.
	 */
	public function POMO_Reader() {
		self::__construct();
	}

	/**
	 * Sets the endianness of the file.
	 *
	 * @param string $endian 'big' or 'little'
	 */
	public function setEndian( $endian ) {
		$this->endian = $endian;
	}

	/**
	 * Reads a 32bit Integer from the Stream
	 *
	 * @return mixed The integer, corresponding to the next 32 bits from
	 * 	the stream of false if there are not enough bytes or on error
	 */
	public function readint32() {
		$bytes = $this->read( 4 );
		if ( 4 != $this->strlen( $bytes ) ) {
			return false;
		}
		$endian_letter = ( 'big' == $this->endian ) ? 'N' : 'V';
		$int           = unpack( $endian_letter, $bytes );
		if ( ! is_array( $int ) ) {
			return false;
		}
		return array_shift( $int );
	}

	/**
	 * Reads an array of 32-bit Integers from the Stream
	 *
	 * @param integer $count How many elements should be read
	 * @return mixed Array of integers or false if there isn't
	 * 	enough data or on error
	 */
	public function readint32array( $count ) {
		$bytes = $this->read( 4 * $count );
		if ( 4 * $count != $this->strlen( $bytes ) ) {
			return false;
		}
		$endian_letter = ( 'big' == $this->endian ) ? 'N' : 'V';
		return unpack( $endian_letter . $count, $bytes );
	}

	public function substr( $string, $start, $length ) {
		if ( $this->is_overloaded ) {
			return mb_substr( (string) $string, (int) $start, $length, 'ascii' );
		} else {
			return substr( (string) $string, (int) $start, $length );
		}
	}

	public function strlen( $string ) {
		if ( $this->is_overloaded ) {
			return mb_strlen( (string) $string, 'ascii' );
		} else {
			return strlen( (string) $string );
		}
	}

	public function str_split( $string, $chunk_size ) {
		$string = (string) $string;
		if ( '' === $string ) {
			// Preserve legacy behavior: str_split('') returned array('') before PHP 8.2.
			return array( '' );
		}
		if ( ! function_exists( 'str_split' ) ) {
			$length = $this->strlen( $string );
			$out    = array();
			for ( $i = 0; $i < $length; $i += $chunk_size ) {
				$out[] = $this->substr( $string, $i, $chunk_size );
			}
			return $out;
		} else {
			return str_split( $string, $chunk_size );
		}
	}

	public function pos() {
		return $this->_pos;
	}

	public function is_resource() {
		return true;
	}

	public function close() {
		return true;
	}
}
endif;

if ( ! class_exists( 'POMO_FileReader', false ) ) :
class POMO_FileReader extends POMO_Reader {

	public $_f;

	public function __construct( $filename ) {
		parent::__construct();
		$this->_f = fopen( $filename, 'rb' );
	}

	/**
	 * PHP4-style constructor kept for backwards compatibility.
	 *
	 * @deprecated Use __construct() instead.
	 */
	public function POMO_FileReader( $filename ) {
		self::__construct( $filename );
	}

	public function read( $bytes ) {
		if ( ! is_resource( $this->_f ) ) {
			return false;
		}
		return fread( $this->_f, $bytes );
	}

	public function seekto( $pos ) {
		if ( ! is_resource( $this->_f ) ) {
			return false;
		}
		if ( -1 == fseek( $this->_f, $pos, SEEK_SET ) ) {
			return false;
		}
		$this->_pos = $pos;
		return true;
	}

	public function is_resource() {
		return is_resource( $this->_f );
	}

	public function feof() {
		if ( ! is_resource( $this->_f ) ) {
			return true;
		}
		return feof( $this->_f );
	}

	public function close() {
		if ( ! is_resource( $this->_f ) ) {
			return false;
		}
		return fclose( $this->_f );
	}

	public function read_all() {
		$all = '';
		while ( ! $this->feof() ) {
			$chunk = $this->read( 4096 );
			if ( false === $chunk ) {
				break;
			}
			$all .= $chunk;
		}
		return $all;
	}
}
endif;

if ( ! class_exists( 'POMO_StringReader', false ) ) :
/**
 * Provides file-like methods for manipulating a string instead
 * of a physical file.
 */
class POMO_StringReader extends POMO_Reader {

	public $_str = '';

	public function __construct( $str = '' ) {
		parent::__construct();
		$this->_str = $str;
		$this->_pos = 0;
	}

	/**
	 * PHP4-style constructor kept for backwards compatibility.
	 *
	 * @deprecated Use __construct() instead.
	 */
	public function POMO_StringReader( $str = '' ) {
		self::__construct( $str );
	}

	public function read( $bytes ) {
		$data        = $this->substr( $this->_str, $this->_pos, $bytes );
		$this->_pos += $bytes;
		if ( $this->strlen( $this->_str ) < $this->_pos ) {
			$this->_pos = $this->strlen( $this->_str );
		}
		return $data;
	}

	public function seekto( $pos ) {
		$this->_pos = $pos;
		if ( $this->strlen( $this->_str ) < $this->_pos ) {
			$this->_pos = $this->strlen( $this->_str );
		}
		return $this->_pos;
	}

	public function length() {
		return $this->strlen( $this->_str );
	}

	public function read_all() {
		return $this->substr( $this->_str, $this->_pos, $this->strlen( $this->_str ) );
	}
}
endif;

if ( ! class_exists( 'POMO_CachedFileReader', false ) ) :
/**
 * Reads the contents of the file in the beginning.
 */
class POMO_CachedFileReader extends POMO_StringReader {

	public function __construct( $filename ) {
		parent::__construct();
		$this->_str = file_get_contents( $filename );
		if ( false === $this->_str ) {
			return;
		}
		$this->_pos = 0;
	}

	/**
	 * PHP4-style constructor kept for backwards compatibility.
	 *
	 * @deprecated Use __construct() instead.
	 */
	public function POMO_CachedFileReader( $filename ) {
		self::__construct( $filename );
	}
}
endif;

if ( ! class_exists( 'POMO_CachedIntFileReader', false ) ) :
/**
 * Reads the contents of the file in the beginning.
 */
class POMO_CachedIntFileReader extends POMO_CachedFileReader {

	public function __construct( $filename ) {
		parent::__construct( $filename );
	}

	/**
	 * PHP4-style constructor kept for backwards compatibility.
	 *
	 * @deprecated Use __construct() instead.
	 */
	public function POMO_CachedIntFileReader( $filename ) {
		self::__construct( $filename );
	}
}
endif;
