const fs = require('fs');
const os = require('os');
const path = require('path');
const webpack = require('webpack');
const Nunjucks = require('nunjucks');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const CssMinimizerPlugin = require('css-minimizer-webpack-plugin');
const COLORS = require('./src/constants/colors.js');

const isProduction = process.env.NODE_ENV === 'production';

// Resolve the machine's LAN address for the dev-server A-Frame template branch.
function localIP() {
	let nets;
	try {
		nets = os.networkInterfaces();
	} catch (e) {
		return 'localhost';
	}
	for (const name of Object.keys(nets)) {
		for (const net of nets[name] || []) {
			if (net.family === 'IPv4' && !net.internal) {
				return net.address;
			}
		}
	}
	return 'localhost';
}

// Set up templating.
const nunjucks = Nunjucks.configure(path.resolve(__dirname, 'src'), {noCache: true});
nunjucks.addGlobal('DEBUG_AFRAME', !!process.env.DEBUG_AFRAME);
nunjucks.addGlobal('DEBUG_KEYBOARD', !!process.env.DEBUG_KEYBOARD);
nunjucks.addGlobal('DEBUG_INSPECTOR', !!process.env.DEBUG_INSPECTOR);
nunjucks.addGlobal('HOST', localIP());
nunjucks.addGlobal('IS_PRODUCTION', isProduction);
nunjucks.addGlobal('COLORS', COLORS);
nunjucks.addGlobal('LIVE_DEMO', !!process.env.LIVE_DEMO);

// Generate timestamp used to cache-bust the emitted bundle and stylesheet.
const timestamp = Math.floor(Date.now() / 1000);
nunjucks.addGlobal('BUILD_TIMESTAMP', timestamp);

// Initial Nunjucks render.
fs.writeFileSync('index.html', nunjucks.render('index.html'));

// For development, watch HTML for changes to recompile Nunjucks.
// The production Express server handles Nunjucks by itself.
if (!isProduction) {
	fs.watch('src/', {recursive: true}, (eventType, filename) => {
		if (!filename || (filename.indexOf('.html') === -1 && filename.indexOf('templates') === -1)) {
			return;
		}
		try {
			fs.writeFileSync('index.html', nunjucks.render('index.html'));
		} catch (e) {
			console.error(e);
		}
	});
}

module.exports = {
	mode: isProduction ? 'production' : 'development',
	devtool: isProduction ? 'source-map' : 'eval-cheap-module-source-map',
	entry: './src/index.js',
	output: {
		path: __dirname,
		filename: `build/build.${timestamp}.js`,
		// Code loaded on demand (the Ogg decoder for old Safari), next to the bundle; paths relative to the page.
		chunkFilename: `build/[name].${timestamp}.js`,
		publicPath: '',
		clean: false,
	},
	plugins: [
		new webpack.ProvidePlugin({Buffer: ['buffer', 'Buffer']}),
		// LIVE_DEMO=1 replaces the connection to the mod with an in-page replay (src/live/demo.js).
		new webpack.DefinePlugin({LIVE_DEMO: JSON.stringify(!!process.env.LIVE_DEMO)}),
		new MiniCssExtractPlugin({filename: `build/style.${timestamp}.css`}),
	],
	module: {
		rules: [
			{
				test: /\.js$/,
				// Vendored aframe components ship browser-ready and must be bundled as-is.
				exclude: [/node_modules/, path.resolve(__dirname, 'src/vendor/aframe-components')],
				use: 'babel-loader',
			},
			{
				test: /\.styl$/,
				exclude: /node_modules/,
				use: [MiniCssExtractPlugin.loader, {loader: 'css-loader', options: {url: false}}, 'postcss-loader', 'stylus-loader'],
			},
		],
	},
	optimization: {
		minimizer: ['...', new CssMinimizerPlugin()],
	},
	resolve: {
		modules: [path.join(__dirname, 'node_modules')],
		fallback: {
			buffer: require.resolve('buffer/'),
		},
	},
	devServer: {
		host: '0.0.0.0',
		port: 3003,
		hot: true,
		allowedHosts: 'all',
		static: {directory: __dirname},
		devMiddleware: {writeToDisk: false},
	},
};
