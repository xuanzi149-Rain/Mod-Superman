Generated source files, not an installable PAK.
Close Toolkit. Copy editor-stats/Stats/Weapon.stats into:
  <game>/Data/Editor/Mods/FirstBloodDamageTest_fa86e11f-65e1-7489-881e-69cb2b80e055/Stats/Stats/Weapon.stats
Copy runtime-stats/Generated/Data/Weapon.txt into:
  <game>/Data/Public/FirstBloodDamageTest_fa86e11f-65e1-7489-881e-69cb2b80e055/Stats/Generated/Data/Weapon.txt
Reopen Toolkit and verify Damage=2d6, then save and Publish Local.
Keep the manual PAK separately. Replace the installed PAK with the newly published one.
Verify the actual game damage formula; other damage sources are not multiplied.
Also verify full-health bonus damage, ordinary shortswords and disable/reload recovery.
No game version compatibility claim has been established.
