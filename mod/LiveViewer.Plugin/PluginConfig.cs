namespace LiveViewer.Plugin
{
    /// <summary>UserData/LiveViewer.json. BSIPA generates the store; properties must stay virtual.</summary>
    public class PluginConfig
    {
        /// <summary>Run the web server. Takes effect on the next game start.</summary>
        public virtual bool Enabled { get; set; } = true;

        /// <summary>
        /// Fetch BeatLeader star ratings for the level browser. This tells BeatLeader the hashes of the levels viewers
        /// look at; it can be switched off in the menu.
        /// </summary>
        public virtual bool BeatLeaderStats { get; set; } = true;

        /// <summary>Shown to viewers as the player's name. Empty: the name the game knows.</summary>
        public virtual string PlayerName { get; set; } = "";

        /// <summary>
        /// Testing only: approve every waiting device without asking. Anyone on the network can then watch and read
        /// the level list. Never on by default and not settable from the menu.
        /// </summary>
        public virtual bool DevAutoApprove { get; set; }

        /// <summary>
        /// Testing only: a level hash (optionally followed by a space and a difficulty) to play with No Fail once the
        /// main menu is up, once per game start. Empty: off.
        /// </summary>
        public virtual string DevAutoPlayLevel { get; set; } = "";
    }
}
