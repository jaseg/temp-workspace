<?php

declare(strict_types=1);

use Rector\Config\RectorConfig;
use Rector\Set\ValueObject\LevelSetList;
use Rector\Set\ValueObject\SetList;

return static function (RectorConfig $rectorConfig): void {
    // Note: File paths will be passed directly via command line
    // This config focuses on rule sets only

    // PHP version upgrades (5.x → 8.3) - VERSION SPECIFIC CHANGES ONLY
    $rectorConfig->sets([
        LevelSetList::UP_TO_PHP_83,
    ]);
};
