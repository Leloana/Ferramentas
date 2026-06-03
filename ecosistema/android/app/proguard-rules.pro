# sshj usa reflexao/SPI; mantenha as classes para o build release nao quebrar.
-keep class net.schmizz.sshj.** { *; }
-keep class com.hierynomus.** { *; }
-keep class org.bouncycastle.** { *; }
-dontwarn org.slf4j.**
-dontwarn net.schmizz.sshj.**
-dontwarn org.bouncycastle.**
